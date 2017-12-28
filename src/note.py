#!/usr/bin/python3
"""A command line note manager.

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

NOTE_DIR = os.environ.get('NOTE_DIR',
                          os.path.join(os.path.expanduser('~'), '.note'))
EDITOR = os.environ.get('EDITOR', 'vim')

TZ_LOCAL = tz.tzlocal()
TZ_UTC = tz.tzutc()

LOGGING_FORMAT = '%(asctime)s [%(filename)s:%(lineno)s - %(funcName)20s() ]' +\
                 '%(message)s'
LOGGING_LEVEL = logging.INFO
#LOGGING_DATE_FORMAT = '%Y-%m-%d %h:%M'
# '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'

class Note:
    """Interface to a single note.

    A note is identified by a (UTC Date, Random Int) tuple.  This class
    is reponsible for mapping this tuple to absolute paths.
    """

    def __init__(self, date=None, rand=None):
        if date is None:
            self.date = datetime.utcnow().replace(tzinfo=TZ_UTC)
        else:
            self.date = date

        if rand is None:
            self.rand = random.randint(0, 0xffffffff)
        else:
            self.rand = rand

    def __str__(self):
        return "Note(date=%s, rand=%08x)" % (self.date, self.rand)

    def dirname(self):
        """Return an absolute path for the note's directory."""
        return os.path.join(NOTE_DIR,
                            "%04d" % self.date.year,
                            "%02d" % self.date.month,
                            "%02d" % self.date.day,
                            "%02d" % self.date.hour)

    def head_encode(self):
        head = self.date.year
        head = (head * 12) + self.date.month - 1
        head = (head * 31) + self.date.day - 1
        head = (head * 24) + self.date.hour
        return head

    @staticmethod
    def head_decode(head):
        hour = head % 24
        head = int(head / 24)
        day = (head % 31) + 1
        head = int(head / 31)
        month = (head % 12) + 1
        year = int(head / 12)
        return year, month, day, hour

    def stub_encode(self):
        """Encode a subset of a note's datetime to a filename stub."""
        stub = self.date.minute
        stub = (stub * 60) + self.date.second
        stub = (stub * 10**6) + self.date.microsecond
        return stub

    @staticmethod
    def stub_decode(stub):
        """Decode a filename stub to a subset of the note's datetime."""
        microsecond = stub % 10**6
        second = int((stub / 10**6) % 60)
        minute = int((stub / 10**6) / 60)
        logging.debug("decode stub %08x to %02d:%02d.%06d" %
                      (stub, minute, second, microsecond))
        return minute, second, microsecond

    def identity(self):
        """Return and identifier for the note."""
        return '%08x-%08x-%08x' % (self.head_encode(), self.stub_encode(),
                                   self.rand)

    def filename(self):
        """Return the note's filename."""
        return '%08x-%08x.txt' % (self.stub_encode(), self.rand)

    def realpath(self):
        """Return the abolute pathname for the note."""
        return os.path.join(self.dirname(), self.filename())

    @staticmethod
    def absolute_path_to_note(path):
        """Given an absolute path return a Note instance."""
        path_re = os.path.join(NOTE_DIR,
                               r'(?P<year>\d{4})',
                               r'(?P<month>\d{2})',
                               r'(?P<day>\d{2})',
                               r'(?P<hour>\d{2})',
                               r'(?P<stub>[0-9A-Fa-f]{8})-' +
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
        stub = int(match.group('stub'), 16)
        minute, second, microsecond = Note.stub_decode(stub)
        assert match.group('type') == '.txt'
        date = datetime(year, month, day, hour, minute, second, microsecond,
                        TZ_UTC)
        rand = int(match.group('rand'), 16)
        return Note(date, rand)





class NoteIterator:
    """Iterate over a set of notes.

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
    STACK_HEAD = 0
    CURSOR_BASE = 0
    CURSOR_YEAR = 1
    CURSOR_MONTH = 2
    CURSOR_DAY = 3
    CURSOR_HOUR = 4
    CURSOR_ITEM = 5

    def __init__(self, since=None, until=None, reverse=False, index_set=None,
                 index_max=None):
        """Initialise a NoteIterator.

        Args:
            since: Starting date to iterator from.
            until: Last date to iterate until.
            reverse: Iterate in reverse order, most recent note first.
            index_set: Sorted list of (min,max) index ranges to print.
            index_max: Maximum node index to print.
        """
        self.cursor = [None] * 6
        self.stacks = [[NOTE_DIR]] + [[]] * 5

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
        logging.debug("__init__()\n%s" % self)

    def __str__(self):
        rv = "NoteIterator:"
        rv += "\n\tcursor: %s" % self.cursor
        rv += "\n\tstacks: "
        rv += "Notes: %s" % self.stacks[self.CURSOR_ITEM]
        rv += "\n\t\tHours: %s" % self.stacks[self.CURSOR_HOUR]
        rv += "\n\t\tDays: %s" % self.stacks[self.CURSOR_DAY]
        rv += "\n\t\tMonths: %s" % self.stacks[self.CURSOR_MONTH]
        rv += "\n\t\tYears: %s" % self.stacks[self.CURSOR_YEAR]
        rv += "\n\t\tBases: %s" % self.stacks[self.CURSOR_BASE]
        return rv

    def __iter__(self):
        """Return the iterator."""
        return self

    def __next__(self):
        """Return the next note or raise StopIteration."""
        done = False
        while not done:
            if self.index_max is not None and self.index_max < self.index + 1:
                raise StopIteration
            self.pop(self.CURSOR_ITEM)
            if not self.cursor[self.CURSOR_ITEM]:
                raise StopIteration
            if self.index_set is None:
                done = True
                break
            # TODO: Pop items of the index set once we pass it.
            for index_min, index_max in self.index_set:
                if index_min <= self.index <= index_max:
                    done = True
                    break
        path = os.path.join(*self.cursor)
        return Note.absolute_path_to_note(path=path)

    def cursor_date(self, level):
        """Crop cursor datetime to level.

        TODO: Support filtering at resolution smaller than hour.
        """
        param = {'year': 0, 'month': 1, 'day': 1, 'hour': 0, 'minute': 0,
                 'second': 0, 'microsecond': 0, 'tzinfo': TZ_UTC}
        if self.CURSOR_YEAR <= level:
            param['year'] = int(self.cursor[self.CURSOR_YEAR])
        if self.CURSOR_MONTH <= level:
            param['month'] = int(self.cursor[self.CURSOR_MONTH])
        if self.CURSOR_DAY <= level:
            param['day'] = int(self.cursor[self.CURSOR_DAY])
        if self.CURSOR_HOUR <= level:
            param['hour'] = int(self.cursor[self.CURSOR_HOUR])
        return datetime(**param)

    @staticmethod
    def level_date(date, level):
        """Crop datetime to level.

        TODO: Support filtering at resolution smaller than hour.
        """
        param = {'minute': 0, 'second': 0, 'microsecond': 0, 'tzinfo': TZ_UTC}
        if level < NoteIterator.CURSOR_YEAR:
            param['year'] = 0
        if level < NoteIterator.CURSOR_MONTH:
            param['month'] = 1
        if level < NoteIterator.CURSOR_DAY:
            param['day'] = 1
        if level < NoteIterator.CURSOR_HOUR:
            param['hour'] = 0
        return date.replace(**param)

    def valid(self, level):
        """Return True if cursor is valid with respect to date range."""
        if level >= self.CURSOR_YEAR:
            date = self.cursor_date(level)
            if ((self.since and date < self.level_date(self.since, level)) or
                (self.until and (date > self.level_date(self.until, level)))):
                return False
        return True

    def pop(self, level):
        """For a given level, move an item from the stack onto the cursor."""
        self.cursor[level] = None
        while self.cursor[level] is None:
            if not self.stacks[level] and level > self.CURSOR_BASE:
                self.pop(level - 1)
            if self.stacks[level]:
                self.cursor[level] = self.stacks[level].pop(self.STACK_HEAD)
                if self.valid(level):
                    if level < self.CURSOR_ITEM:
                        self.push(level + 1)
                    else:
                        self.index += 1
                else:
                    self.cursor[level] = None
            else:
                break
        logging.debug("pop(level=%d)\n%s" % (level, self))

    def push(self, level):
        """For a given level, push a new set of items onto the stack."""
        assert not self.stacks[level]
        path = os.path.join(*self.cursor[:level])
        try:
            self.stacks[level] = os.listdir(path)
            self.stacks[level].sort()
            if self.reverse:
                self.stacks[level] = self.stacks[level][::-1]
            logging.debug("push(level=%d)\n%s" % (level, self))
        except FileNotFoundError:
            pass

    @staticmethod
    def argparse_datetime(arg, round_up):
        """Parse local datetime string and return UTC datetime.

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
        """Round down missing part of local datetime string to UTC datetime."""
        return NoteIterator.argparse_datetime(arg, round_up=False)

    @staticmethod
    def argparse_until(arg):
        """Round up missing part of local datetime string to UTC datetime."""
        return NoteIterator.argparse_datetime(arg, round_up=True)

    @staticmethod
    def argparse_range(arg):
        """Parse range string into ordered list of (min,max) tuples."""
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
    """Create a new note (WIP)."""
    note = Note()
    # TODO: May leave empty directories.
    os.makedirs(note.dirname(), exist_ok=True)
    subprocess.check_call([EDITOR, note.realpath()])

def main_list(notes, identify=False, filename=False):
    """List notes to stdout (WIP)."""
    separate = False
    if filename:
        for note in notes:
            print(note.realpath())
        return
    if identify:
        for note in notes:
            print(note.identity())
        return
    for note in notes:
        if separate:
            print()
        date = note.date.astimezone(TZ_LOCAL)
        date = date.strftime('%Y-%m-%dT%H:%M')
        print("[%d]\tDate: %s" % (notes.index, date))
        print("\tFile: %s" % note.realpath())
        print("\tNNID: %s" % note.identity())
        print()
        file = open(note.realpath(), 'r')
        print(file.read())
        file.close()
        separate = True

def main_edit(notes):
    """Edit a set of notes (WIP)."""
    paths = []
    for note in notes:
        paths.append(note.realpath())
    if paths:
        subprocess.check_call([EDITOR] + paths)

def main():
    """Parse command line arguments."""
    ap = ArgumentParser(prog='note',
                        description='Manage your notes.',
                        epilog='Feedback welcome.')

    # Iterator Arguments.
    ap.add_argument('date', type=str, nargs='?',
                    help='Note date to operate on.')
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

    # Note Operation.
    ap.add_argument('-a', '--add', action='store_true', help='Add a note.')
    ap.add_argument('-e', '--edit', type=NoteIterator.argparse_range,
                    nargs='?', help='Edit note(s).', default=SUPPRESS)
    #ap.add_argument('-d', '--delete', action=store_true, help='Delete a note')

    # Output Modifies.
    ap.add_argument('-fn', '--filename', action='store_true',
                    help='Output filename only')
    #ap.add_argument('-ft', '--filetype', action='store_true',
    #                help='Output filename only')
    #ap.add_argument('-fr', '--filerand', action='store_true',
    #                help='Output filename only')
    ap.add_argument('-id', '--identify', action='store_true',
                    help='Output identities only')

    args = ap.parse_args()

    # Date.
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

    # Create iterator.
    notes = NoteIterator(reverse=(args.order == 'reverse'),
                         since=args.since,
                         until=args.until,
                         index_max=args.count,
                         index_set=args.index)


    if hasattr(args, 'edit'):
        main_edit(notes)
    else:
        main_list(notes, identify=args.identify, filename=args.filename)

if __name__ == "__main__":
    main()

