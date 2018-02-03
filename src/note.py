#!/usr/bin/python3
""" A command line note manager.

Toying with ideas of how to manage notes.

"""

from argparse import ArgumentParser, ArgumentTypeError, SUPPRESS
from datetime import datetime, timedelta
from dateutil import tz
from functools import reduce
import logging
import os
import random
import re
import subprocess


#
# NOTE_STORE
#
NOTE_DIR = os.environ.get('NOTE_DIR',
                          os.path.join(os.path.expanduser('~'), '.note'))

#
# Directory depth: single directory (0), group by year (1), group by month (2),
# group by day (3), etc.
#
NOTE_CUT = os.environ.get('NOTE_CUT', 2)
NOTE_CUT_LABEL = ['year', 'month', 'day', 'minute', 'second', 'microsecond',
                  'note']
NOTE_CUT_FMT = ['%04d', '%02d', '%02d', '%02d', '%02d', '%06d',
                '%08x-%08x-%08x%s']
NOTE_CUT_RE = [r'^\d{4}$', r'^\d{2}$', r'^\d{2}$', r'^\d{2}$',
               r'^\d{2}$', r'^\d{2}$', r'^\d{6}$',
               r'^(?P<nnid>[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8})(?P<type>\.\S+)$']

EDITOR = os.environ.get('EDITOR', 'vim')

TZ_LOCAL = tz.tzlocal()
TZ_UTC = tz.tzutc()

LOGGING_FORMAT = '%(asctime)s [%(filename)s:%(lineno)s - %(funcName)20s() ]' +\
                 '%(message)s'
LOGGING_LEVEL = logging.INFO
#LOGGING_LEVEL = logging.DEBUG
#LOGGING_DATE_FORMAT = '%Y-%m-%d %h:%M'
# '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=LOGGING_LEVEL)

class Note:
    """Interface to a single note.



        head-tail-rand.type

    A note is identified by a (UTC Date, Random Int) tuple.  This class
    is reponsible for mapping this tuple to absolute paths.
    """

    RAND_MIN = 0x00000000
    RAND_MAX = 0xffffffff

    def __init__(self, date=None, rand=None, exts=None):
        """ Initialise a note.

        Args:
            date: Note date in UTC. The current time will be used if none is
                  supplied.
            rand: 32-bit random identifier. A random value will be generated if
                  none is supplied.
            exts: Filename extension list ['.txt','.jpg', ...]. If note with no
                  type is considered to be abstract and primarily used for
                  iteration.

        """
        if date is None:
            self.date = datetime.utcnow().replace(tzinfo=TZ_UTC)
        else:
            self.date = date
        if rand is None:
            self.rand = random.randint(self.RAND_MIN, self.RAND_MAX)
        else:
            self.rand = rand
        self.exts = set(exts)

    def __str__(self):
        return "Note(date=%s, rand=%08x, type=%s)" % (self.date, self.rand,
                                                      self.exts)

    def dirname(self):
        """ Return an absolute path for the note's directory. """
        name = [NOTE_DIR]
        for level in range(NOTE_CUT):
            field = NOTE_CUT_LABEL[level]
            value = getattr(self.date, field)
            name.append(NOTE_CUT_FMT[level] % value)
        return os.path.join(*name)

    def head_encode(self):
        """ Encode head date fields into a 32-bit integer. """
        head = self.date.year
        head = (head * 12) + self.date.month - 1
        head = (head * 31) + self.date.day - 1
        head = (head * 24) + self.date.hour
        return head

    @staticmethod
    def head_decode(head):
        """ Decode a 32-bit integer into head date fields. """
        hour = head % 24
        head = int(head / 24)
        day = (head % 31) + 1
        head = int(head / 31)
        month = (head % 12) + 1
        year = int(head / 12)
        return year, month, day, hour

    def tail_encode(self):
        """ Encode tail date fields into a 32-bit integer. """
        tail = self.date.minute
        tail = (tail * 60) + self.date.second
        tail = (tail * 10**6) + self.date.microsecond
        return tail

    @staticmethod
    def tail_decode(tail):
        """ Decode tail date fields into a 32-bit integer. """
        microsecond = tail % 10**6
        second = int((tail / 10**6) % 60)
        minute = int((tail / 10**6) / 60)
        logging.debug("decode tail %08x to %02d:%02d.%06d" %
                      (tail, minute, second, microsecond))
        return minute, second, microsecond

    def nnid_encode(self):
        """ Encode date and rand fields into an ID. """
        return '%08x-%08x-%08x' % (self.head_encode(), self.tail_encode(),
                                   self.rand)
    @staticmethod
    def nnid_decode(nnid):
        """ Decode ID into date and rand fields. """
        nnid_re = r'^(?P<head>[0-9A-Fa-f]{8})-(?P<tail>[0-9A-Fa-f]{8})-(?P<rand>[0-9A-Fa-f]{8})$'
        match = re.match(nnid_re, nnid)
        if not match:
            raise ArgumentTypeError("could not parse NNID \"%s\"" % nnid)
        year, month, day, hour = Note.head_decode(int(match.group('head'), 16))
        minute, second, microsecond = Note.tail_decode(int(match.group('tail'), 16))
        date = datetime(year, month, day, hour, minute, second, microsecond,
                        TZ_UTC)
        rand = int(match.group('rand'), 16)
        return date, rand

    def filename(self):
        """ Return a list of the note's filenames. """
        head = self.head_encode()
        tail = self.tail_encode()
        return '%08x-%08x-%08x' % (head, tail, self.rand)

    def realpath(self):
        """ Return a list of the note's abolute filenames. """
        return os.path.join(self.dirname(), self.filename())

    def extensions(self):
        """ Return the set of filename extensions for this note. """
        return self.exts

    @staticmethod
    def absolute_path_to_note(path):
        """ Given an absolute path return a Note instance. """
        path_re = os.path.join(NOTE_DIR,
                               r'(?P<year>\d{4})',
                               r'(?P<month>\d{2})',
                               r'(?P<day>\d{2})',
                               r'(?P<hour>\d{2})',
                               r'(?P<tail>[0-9A-Fa-f]{8})-' +
                               r'(?P<rand>[0-9A-Fa-f]{8})(?P<type>\S*)')
        logging.debug(path_re)
        pattern = re.compile(r'^'+path_re+r'$')
        match = pattern.match(path)
        if not match:
            raise ArgumentTypeError("Unexpected note path \"%s\"" % path)
        year = int(match.group('year'))
        month = int(match.group('month'))
        day = int(match.group('day'))
        hour = int(match.group('hour'))
        tail = int(match.group('tail'), 16)
        minute, second, microsecond = Note.tail_decode(tail)
        assert match.group('type') == '.txt'
        date = datetime(year, month, day, hour, minute, second, microsecond,
                        TZ_UTC)
        rand = int(match.group('rand'), 16)
        return Note(date, rand)

    @staticmethod
    def filename_to_note(name):
        """ Return a Note for the given name. """
        match = re.match(NOTE_CUT_RE[-1], name)
        if not match:
            raise ArgumentTypeError("Unexpected filename \"%s\"" % name)
        note_nnid = match.group('nnid')
        node_type = match.group('type')
        note_date, note_rand = Note.nnid_decode(note_nnid)
        return Note(note_date, note_rand, [node_type])


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
                 index_max=None, type_filter=None):
        """ Initialise a NoteIterator.

        Args:
            since: Starting date to iterator from.
            until: Last date to iterate until.
            reverse: Iterate in reverse order, most recent note first.
            index_set: Sorted list of (min,max) index ranges to print.
            index_max: Maximum node index to print.

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
        assert type_filter is None, "Future implementation."

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
        if ((self.since and date < self.crop_date(self.since, level)) or
            (self.until and date > self.crop_date(self.until, level))):
            return False
        return True

    def valid_note(self, note):
        """ Return True if note should be included in iteration. """
        if ((self.since and note.date < self.since) or
            (self.until and note.date > self.until)):
            return False
        return True

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
                    note_nnid, note_types = self.stacks[-1].pop()
                    note_date, note_rand = Note.nnid_decode(note_nnid)
                    note = Note(note_date, note_rand, note_types)
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
        names or a list of (nnid,types) tuples.

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
                note_type = match.group('type')
                if comb and comb[-1][0] == note_nnid:
                    comb[-1][1].add(note_type)
                else:
                    comb.append((note_nnid, set([note_type])))
            stack = comb
        else:
            stack = [fn for fn in stack if pattern.match(fn)]
        if not self.reverse:
            stack = stack[::-1]
        self.stacks.append(stack)
        logging.debug("NoteIterator.stack_push: %s" % self)

    @staticmethod
    def argparse_datetime(arg, round_up):
        """ Parse local datetime string and return UTC datetime.

        Stick to the ISO datetime definition (yyyy-mm-ddThh:mm:ss.uuuuuu) with
        some shortcuts.  Year can be 2 digits.  Only provide as much of the
        datetime as you need: e.g., 17 is a valid string for the 17th year in
        the current century.
        """

        # Construct a regex and parse argument.
        regex = [r'^(?P<year>\d{4}|\d{2})', r'-(?P<month>\d{1,2})',
                 r'-(?P<day>\d{1,2})', r'T(?P<hour>\d{1,2})',
                 r':(?P<minute>\d{1,2})', r':(?P<second>\d{1,2})',
                 r'\.(?P<microsecond>\d{6})']
        regex = reduce(lambda a, b: b+'('+a+')?', regex[::-1][1:], regex[-1])
        regex += '$'
        pattern = re.compile(regex)
        match = pattern.match(arg)
        if not match:
            raise ArgumentTypeError("could not parse datetime \"%s\"" % arg)

        # Optional parameters.
        param = {'month': 1, 'day': 1, 'hour': 0, 'minute': 0, 'second': 0,
                 'microsecond': 0}
        for field in param.keys():
            value = match.group(field)
            if value:
                param[field] = int(value)

        # Mandatory parameters.
        param['tzinfo'] = TZ_LOCAL
        year = match.group('year')
        if year:
            year = int(year)
            if year < 100:
                cent = datetime.now().year
                year += cent - (cent % 100)
            param['year'] = year
        else: # Should be impossible given regex.
            raise ArgumentTypeError("no year in datetime \"%s\"" % arg)

        # Validate (TODO: check day is valid w.r.t. month).
        limit = {'month': 12, 'day': 31, 'hour': 24, 'minute': 59,
                 'second': 59}
        for field in limit.keys():
            if param[field] > limit[field]:
                raise ArgumentTypeError("%s %d is greater expected limit %d" %
                                        (field, param[field], limit[field]))

        # Return UTC value.
        date = datetime(**param)

        # Until date, so we want to round up to next year, month, day or hour.
        if round_up:
            level = len([x for x in match.groupdict().values()
                         if x is not None])
            if level == 1:
                date = date.replace(year=date.year+1)
            if level == 2:
                if date.month < 12:
                    date = date.replace(month=date.month+1)
                else:
                    date = date.replace(year=date.year+1, month=1)
            if level == 3:
                date = date + timedelta(days=1)
            if level == 4:
                date = date + timedelta(hours=1)
            if level == 5:
                date = date + timedelta(minutes=1)
            if level == 6:
                date = date + timedelta(seconds=1)
            if level < 7:
                date = date - timedelta(microseconds=1)
            logging.debug("UNTIL: %s" % date)

        return date.astimezone(TZ_UTC)

    @staticmethod
    def argparse_since(arg):
        """ Round down missing part of local datetime string to UTC datetime. """
        return NoteIterator.argparse_datetime(arg, round_up=False)

    @staticmethod
    def argparse_until(arg):
        """ Round up missing part of local datetime string to UTC datetime. """
        return NoteIterator.argparse_datetime(arg, round_up=True)

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


def main_add():
    """ Create a new note (WIP). """
    note = Note(exts=['.txt'])
    # TODO: May leave empty directories.
    os.makedirs(note.dirname(), exist_ok=True)
    subprocess.check_call([EDITOR, note.realpath() + '.txt'])

def main_list(notes, identify=False, filename=False, realpath=False):
    """ List notes to stdout (WIP). """
    separate = False
    if filename:
        for note in notes:
            name = note.filename()
            for ext in note.extensions():
                print(name + ext)
        return
    if realpath:
        for note in notes:
            path = note.realpath()
            for ext in note.extensions():
                print(path + ext)
        return
    if identify:
        for note in notes:
            print(note.nnid_encode())
        return
    for note in notes:
        if separate:
            print()
        date = note.date.astimezone(TZ_LOCAL)
        date = date.strftime('%Y-%m-%dT%H:%M')
        print("[%d]\tNNID: %s" % (notes.index, note.filename()))
        print("\tDate: %s" % date)
        path = note.realpath()
        print("\tPath: %s" % path)
        exts = note.extensions()
        print("\tExts: %s" % exts)
        print()
        for ext in exts:
            if ext in ['.txt', '.rst', '.md', '.mw']:
                file = open(path + ext)
                print(file.read())
                file.close()
                separate = True

def main_edit(notes):
    """ Edit a set of notes (WIP). """
    paths = []
    for note in notes:
        path = note.realpath()
        for ext in note.extensions():
            if ext in ['.txt','.rst']:
                paths.append(path + ext)
    if paths:
        subprocess.check_call([EDITOR] + paths)

def main():
    """ Parse command line arguments. """
    ap = ArgumentParser(prog='note',
                        description='Manage your notes.',
                        epilog='Feedback welcome.')

    # Iterator Arguments.
    ap.add_argument('date', type=str, nargs='?',
                    help='Note date or nnid to operate on.')
    ap.add_argument('-s', '--since', type=NoteIterator.argparse_since,
                    help='Earliest date to iterate from. Overrides date.')
    ap.add_argument('-u', '--until', type=NoteIterator.argparse_until,
                    help='Latest date to iterate until. Overrides date.')
    ap.add_argument('-i', '--index', type=NoteIterator.argparse_range,
                    help='Select index of notes: e.g., \"1-2,5,6-8\".')
    ap.add_argument('-c', '--count', type=int,
                    help='Stop after n notes.')
    ap.add_argument('-o', '--order', choices=['forward', 'reverse'],
                    default='reverse', help='Order notes.')
    ap.add_argument('-n', '--note', type=str, help='Note to act on.')

    # Note Operation.
    ap.add_argument('-a', '--add', action='store_true', help='Add a note.')
    ap.add_argument('-e', '--edit', type=NoteIterator.argparse_range,
                    nargs='?', help='Edit note(s).', default=SUPPRESS)
    #ap.add_argument('-d', '--delete', action=store_true, help='Delete a note')

    # Output Modifies.
    ap.add_argument('-rp', '--realpath', action='store_true',
                    help='Output filename only')
    ap.add_argument('-fn', '--filename', action='store_true',
                    help='Output filename only')
    #ap.add_argument('-ft', '--filetype', action='store_true',
    #                help='Output filename only')
    #ap.add_argument('-fr', '--filerand', action='store_true',
    #                help='Output filename only')
    ap.add_argument('-id', '--identify', action='store_true',
                    help='Output identities only')

    args = ap.parse_args()

    # 
    # Note date or identity.
    #
    if args.date is not None:
        if args.since is None:
            args.since = NoteIterator.argparse_since(args.date)
        if args.until is None:
            args.until = NoteIterator.argparse_until(args.date)

    if args.add:
        main_add()
        return

    # Allow edit command to override index.
    if hasattr(args, 'edit') and args.edit is not None:
        args.index = args.edit

    # Single note.
    if args.note:
        notes = [Note.filename_to_note(args.note)]
    else: # Create iterator.
        notes = NoteIterator(reverse=(args.order == 'reverse'),
                             since=args.since,
                             until=args.until,
                             index_max=args.count,
                             index_set=args.index)

    if hasattr(args, 'edit'):
        main_edit(notes)
    else:
        main_list(notes, identify=args.identify, realpath=args.realpath,
                  filename=args.filename)

if __name__ == "__main__":
    main()

