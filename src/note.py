"""
from pathlib import Path
import pickle
import random
import subprocess
"""
import os
from functools import reduce
from datetime import datetime, timedelta
import re

from note_layout import *
NOTE_CUT_LABEL

from note_config import TZ_LOCAL, TZ_UTC
from note_metadata import NoteMetadata

import note_logging as logging

# Grep'able note extensions.
NOTE_EXT_GREP = ['.txt', '.rst', '.mw']

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
        self.exts = exts
        self._meta = None

    def __str__(self):
        return "Note(date=%s, rand=%08x, type=%s)" % (self.date, self.rand,
                                                      self.exts)
    def __repr__(self):
        return self.__str__()

    @property
    def meta(self):
        """ Load metadata and return. """
        if self._meta is None:
            self._meta = NoteMetadata(self.realpath())
        return self._meta

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
        """ Return note's filename.

            TODO: Should this be a @property? Same for realpath?
        """
        head = self.head_encode()
        tail = self.tail_encode()
        return '%08x-%08x-%08x' % (head, tail, self.rand)

    def realpath(self):
        """ Return a note's abolute filename. """
        return os.path.join(self.dirname(), self.filename())

    def extensions(self, grep=False):
        """ Return the set of filename extensions for this note. """
        if grep:
            exts = [ext for ext in self.exts if ext in NOTE_EXT_GREP]
        else:
            exts = self.exts
        return exts

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
        note_ext = match.group('ext')
        note_date, note_rand = Note.nnid_decode(note_nnid)
        return Note(note_date, note_rand, [note_ext])

    @staticmethod
    def argparse(arg, round_up=False):
        """ Parse local datetime string and return UTC datetime.

        Stick to the ISO datetime definition (yyyy-mm-ddThh:mm:ss.uuuuuu) with
        some shortcuts.  Year can be 2 digits.  Only provide as much of the
        datetime as you need: e.g., 17 is a valid string for the 17th year in
        the current century.

        TODO: Fixup comments, possibly break-up function.

        round_up=False -> since
        round_up=True -> until
        has no effect if arg is an nnid.

        """

        # Check for NNID.
        try:
            date, rand = Note.nnid_decode(arg)
            return Note(date, rand)
        except ArgumentTypeError:
            pass

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

        return Note(date=date.astimezone(TZ_UTC), rand=Note.RAND_MIN)




