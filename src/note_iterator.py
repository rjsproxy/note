from datetime import datetime
import os
import re

from note_config import TZ_UTC, TZ_LOCAL
from note import Note
from note_layout import *

import note_logging as logging

class NoteIterator:
    """ Iterate over a set of notes.

    This class uses a cursor and an array of stacks to track iterations.  The
    cursor is a list of strings that joined together give an absolute path.

        cursor = [NOTE_DIR,'2017','12','27','02','6c8e79eb-2408f00d.txt']
        stack = [[],['2016','2015'],[],[],[],[],[]]

    The stack gives a list of items found via os.listdir().  It indicates there
    are no more notes for this year, but 2016 and 2015 are yet to be visited.
    A call to pop(CURSOR_YEAR) would produce.

        cursor = [NOTE_DIR,'2016',None,None,None,None]
        stack = [[],['2015'],[],[],[],[],[]]

    This would be followed by a push(CURSOR_MONTH) and a call to os.listdir().
    So if the first 3 months had notes then we'd end up with.

        cursor = [NOTE_DIR,'2016',None,None,None,None]
        stack = [[],['2015'],['01','02','03'],[],[],[],[]]

    This pop()/push() is then repeated for month, day, hour and item levels.
    """

    # TODO: Better name? Applies to both cursor and stacks.
    CURSOR_LABEL = ['root'] + NOTE_CUT_LABEL

    def __init__(self, since=None, until=None, reverse=False, index_set=None,
                 index_max=None, select=None, exclude=None, grep=None):
        """ Initialise a NoteIterator.

        Args:
            since: Starting note to iterate from.
            until: Last note to iterate until.
            reverse: Iterate in reverse order, most recent note first.
            index_set: Sorted list of (min,max) index ranges to print.
            index_max: Maximum node index to print.
            select: Select only notes with this attribute.
            exclude: Exclude notes with this attribute.

        Invariants:
            len(self.stacks) = len(self.cursor) + 1

        Initial condition: ready to push NOTE_DIR onto the cursor and then
        start searching up directories from there. Initial step is to pop
        selfSee find_note().

         1  self.cursor = []
            self.stacks = [[NOTE_DIR]]
            
         2  self.cursor = [NOTE_DIR]
            self.stacks = [[], [...]]

         2  self.cursor = [NOTE_DIR, YEAR]
        """
        self.cursor = []
        self.stacks = [[NOTE_DIR]]

        self.since = since
        self.until = until
        self.reverse = reverse
        self.index = 0
        self.index_set = index_set
        if index_set:
            self.index_max = index_set[-1][1]
            if index_max:
                self.index_max = min(self.index_max, index_max)
        else:
            self.index_max = index_max

        if grep:
            self.grep = re.compile(grep)
        else:
            self.grep = None

        # Attributes
        self.select_extensions, self.select_attributes = \
                self.parse_attributes(select)
        self.exclude_extensions, self.exclude_attributes = \
                self.parse_attributes(exclude)

        # Compile patterns expected at cursor/stack depths.
        self.pattern = [None]
        for level in range(NOTE_CUT):
            self.pattern.append(re.compile(NOTE_CUT_RE[level]))
        self.pattern.append(re.compile(NOTE_CUT_RE[-1]))
        logging.debug("__init__()\n%s" % self)

    def __str__(self):
        rv = "NoteIterator("
        rv += "\n\tcursor: %s" % self.cursor
        for level in range(len(self.stacks)):
            rv += "\n\t%ss: %s" % (self.CURSOR_LABEL[level],
                                  self.stacks[level])
        rv += ")"
        return rv

    def __iter__(self):
        """ Return the iterator. """
        return self

    def __next__(self):
        """ Return the next note or raise StopIteration. """
        done = False
        while not done:
            if self.index_max is not None and self.index_max < self.index + 1:
                raise StopIteration
            note = self.find_note()
            if note is None:
                raise StopIteration
            if self.index_set is None:
                done = True
                break
            # TODO: Pop items of the index set once we pass it.
            for index_min, index_max in self.index_set:
                if index_min <= self.index <= index_max:
                    done = True
                    break
        return note

    def parse_attributes(self, attributes):
        """ Divide attributes into extension and attribute filters."""
        exts = set()
        meta = set()
        if attributes:
            for attr in attributes:
                if attr.key[0] == '.':
                    if attr.value:
                        raise ArgumentTypeError(
                                "Unexpected extension value: %s" % attr)
                    exts.add(attr.key)
                else:
                    meta.add(attr)
        return exts, meta

    def cursor_path(self):
        """ Return the current absolute cursor path. """
        assert len(self.cursor) > 0
        return os.path.join(*self.cursor)

    def cursor_date(self):
        """ Convert cursor to datetime. """
        param = { 'year': 1, 'month': 1, 'day': 1, 'hour': 0, 'minute': 0,
                  'second': 0, 'microsecond': 0, 'tzinfo': TZ_UTC }
        for level in range(1, len(self.cursor)):
            field = self.CURSOR_LABEL[level]
            value = int(self.cursor[level])
            param[field] = value
        return datetime(**param)

    def crop_date(self, date, depth):
        """ Crop datetime to cursor's level. """
        param = { 'year': 1, 'month': 1, 'day': 1, 'hour': 0, 'minute': 0,
                  'second': 0, 'microsecond': 0, 'tzinfo': TZ_UTC }
        for level in range(1, depth):
            field = self.CURSOR_LABEL[level]
            value = getattr(date, field)
            param[field] = value
        return date.replace(**param)

    def valid_cursor(self):
        """ Return True if cursor should be included in iteration.
        
        Currently this only includes checks for (since, until) date ranges, but
        other filters could be added in the future.
        
        """
        level = len(self.cursor)
        date = self.cursor_date()
        if ((self.since and date < self.crop_date(self.since.date, level)) or
            (self.until and date > self.crop_date(self.until.date, level))):
            return False
        return True

    def valid_note(self, note):
        """ Return True if note should be included in iteration. """

        # Date filters.
        if self.since:
            if note.date < self.since.date:
                return False
            if note.date == self.since.date and note.rand < self.since.rand:
                return False

        if self.until:
            if note.date > self.until.date:
                return False
            if note.date == self.until.date and note.rand > self.until.rand:
                return False

        # Extension filters.
        if self.select_extensions:
            note.exts = [ext for ext in note.exts
                         if ext in self.select_extensions]
        if self.exclude_extensions:
            note.exts = [ext for ext in note.exts
                         if ext not in self.exclude_extensions]
        if not note.exts:
            return False

        # Attribute filters.
        if self.select_attributes:
            match = False
            for attr in self.select_attributes:
                if note.meta.select_attribute(attr):
                    match = True
                    break
            if match == False:
                return False

        if self.exclude_attributes:
            for attr in self.exclude_attributes:
                if note.meta.select_attribute(attr):
                    return False

        # Contents filters.
        if not self.valid_note_contents(note):
            return False

        return True

    def valid_note_contents(self, note):
        """ Return note contains the grep pattern or no pattern defined. """
        if self.grep:
            path = note.realpath()
            for ext in note.extensions(grep=True):
                with open(path + ext, 'r') as textfile:
                    for line in textfile:
                        if self.grep.search(line):
                            return True
        else:
            return True

        return False

    def max_depth(self):
        """
        
        [NOTE_DIR, NOTE_CUTs, notes]
        
        """
        assert len(self.stacks) == len(self.cursor) + 1 # TODO: Required?
        return len(self.stacks) == NOTE_CUT + 2

    def find_note(self):
        """ Search for the next note. """
        while self.cursor or self.stacks[-1]:

            # Descend directory.
            while not self.max_depth() and self.stacks[-1]:
                    path = self.stacks[-1].pop()
                    self.cursor.append(path)
                    if self.valid_cursor():
                        self.stack_push()
                    else:
                        self.cursor.pop()

            # Find a note.
            if self.max_depth():
                while self.stacks[-1]:
                    note_nnid, note_exts = self.stacks[-1].pop()
                    note_date, note_rand = Note.nnid_decode(note_nnid)
                    note = Note(note_date, note_rand, note_exts)
                    if self.valid_note(note):
                        self.index += 1
                        return note

            # Ascend directories.
            while self.cursor and not self.stacks[-1]:
                self.cursor.pop()
                self.stacks.pop()

        return None

    def stack_push(self):
        """ Push cursor contents onto stack.
        
        This function will always increase len(self.stacks) by 1. Depending on
        stack level the contents appended will either be a list of directory
        names or a list of (nnid,exts) tuples.

        """
        try:
            stack = os.listdir(self.cursor_path())
        except FileNotFoundError:
            self.stacks.append([])
            return
        stack.sort()
        pattern = self.pattern[len(self.stacks)]
        if len(self.pattern) == len(self.stacks) + 1:
            comb = []
            for fn in stack:
                match = self.pattern[-1].match(fn)
                if not match:
                    continue
                note_nnid = match.group('nnid')
                note_ext = match.group('ext')
                if comb and comb[-1][0] == note_nnid:
                    comb[-1][1].add(note_ext)
                else:
                    comb.append((note_nnid, set([note_ext])))
            stack = comb
        else:
            stack = [fn for fn in stack if pattern.match(fn)]
        if not self.reverse:
            stack = stack[::-1]
        self.stacks.append(stack)
        logging.debug("NoteIterator.stack_push: %s" % self)


    @staticmethod
    def argparse_range(arg):
        """ Parse range string into ordered list of (min,max) tuples. """
        match = re.match(r'((^|,)\d+(-\d+)?)+$', arg)
        if not match:
            raise ArgumentTypeError("could not parse range \"%s\"" % arg)
        result = []
        for item in match.group().split(','):
            pair = item.split('-')
            if len(pair) == 1:
                pair *= 2
            if pair[0] > pair[1]:
                raise ArgumentTypeError("bad range \"%s\"" % item)
            result.append((int(pair[0]), int(pair[1])))
        result.sort()
        # TODO: Merge overlapping ranged.
        return result



