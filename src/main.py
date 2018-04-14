#!/usr/bin/python3
""" A command line note manager.

Toying with ideas of how to manage notes.

"""
import subprocess
from argparse import ArgumentParser, ArgumentTypeError, SUPPRESS
from datetime import datetime, timedelta
from dateutil import tz
from termcolor import colored
import os

from note_attribute import NoteAttribute
from note_config import TZ_UTC, TZ_LOCAL
from note import Note
from note_iterator import NoteIterator

EDITOR = os.environ.get('EDITOR', 'vim')

def main_add():
    """ Create a new note (WIP). """
    note = Note(exts=['.txt'])
    # TODO: May leave empty directories.
    os.makedirs(note.dirname(), exist_ok=True)
    subprocess.check_call([EDITOR, note.realpath() + '.txt'])

def main_list(notes, identify=False, filename=False, realpath=False):
    """ List notes to stdout (WIP). """
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

    # Print one note per line.
    for note in notes:
        line = ''
        path = note.realpath()
        for ext in note.extensions():
            if ext in ['.txt', '.rst', '.md', '.mw']:
                with open(path + ext) as file:
                    for line in file:
                        line = line.strip()
                        if len(line) > 0:
                            break
                if len(line) > 0:
                    break
        attr = [str(a) for a in note.meta.attributes()]
        if len(attr) > 0:
            attr = '(' + ', '.join(attr) + ')'
        else:
            attr = ''
        print("[%2d] %s %s" % (notes.index, line, attr))
    return

    # full dump.
    separate = False
    for note in notes:
        if separate:
            print()
        date = note.date.astimezone(TZ_LOCAL)
        date = date.strftime('%Y-%m-%dT%H:%M')
        text = "[%d]\tNNID: %s" % (notes.index, note.filename())
        text += "\n\tDate: %s" % date
        path = note.realpath()
        text += "\n\tPath: %s" % path
        exts = note.extensions()
        text += "\n\tExts: %s" % exts
        text += "\n\tAttr:"
        for attr in note.meta.attributes():
            text += " %s" % attr
        text += "\n"
        print(colored(text, 'yellow'))
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
                        epilog='''Feedback welcome.''')

    # Iterator Arguments.
    ap.add_argument('note', type=str, nargs='?',
                    help='Note date or NNID to operate on.')
    ap.add_argument('-s', '--since', type=Note.argparse,
                    help='Earliest date to iterate from. Overrides date.')
    ap.add_argument('-u', '--until', type=lambda x: Note.argparse(x, True),
                    help='Latest date to iterate until. Overrides date.')
    ap.add_argument('-i', '--index', type=NoteIterator.argparse_range,
                    help='Select index of notes: e.g., \"1-2,5,6-8\".')
    ap.add_argument('-c', '--count', type=int,
                    help='Stop after n notes.')
    ap.add_argument('-o', '--order', choices=['forward', 'reverse'],
                    default='reverse', help='Order notes.')

    # Grepping.
    ap.add_argument('-g', '--grep', type=str,
                    help='Select files matching pattern')

    # Tagging.
    ap.add_argument('-ts', '--tag-select', type=NoteAttribute.decode,
                    nargs='*', help='Tag a note.')
    ap.add_argument('-te', '--tag-exclude', type=NoteAttribute.decode,
                    nargs='*', help='Exclude note with tag.')
    ap.add_argument('-ta', '--tag-assign', type=NoteAttribute.decode,
                    nargs='*', help='Assign tags to note(s).')
    ap.add_argument('-tr', '--tag-remove', type=NoteAttribute.decode,
                    nargs='*', help='Remove tags from note(s).')

    # Note Operation.
    ap.add_argument('-a', '--add', action='store_true', help='Add a note.')
    ap.add_argument('-e', '--edit', type=NoteIterator.argparse_range,
                    nargs='?', help='Edit note(s). If not argument, edit all notes iterated on.', default=SUPPRESS)
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
    #print(args)
    #return

    # 
    # Note date or identity.  RJS: Using notes as iterators?
    #
    if args.note is not None:
        if args.since is None:
            args.since = Note.argparse(args.note)
        if args.until is None:
            args.until = Note.argparse(args.note, True)

    if args.add:
        main_add()
        return

    # Allow edit command to override index.
    if hasattr(args, 'edit') and args.edit is not None:
        args.index = args.edit

    # Single note.
    notes = NoteIterator(reverse=(args.order == 'reverse'),
                         since=args.since,
                         until=args.until,
                         index_max=args.count,
                         index_set=args.index,
                         select=args.tag_select,
                         exclude=args.tag_exclude,
                         grep=args.grep)

    if args.tag_remove or args.tag_assign:
        for note in notes:
            if args.tag_remove:
                for attr in args.tag_remove:
                    note.meta.remove_attribute(attr)
            if args.tag_assign:
                for attr in args.tag_assign:
                    note.meta.assign_attribute(attr)
            note.meta.save()
        return

    if hasattr(args, 'edit'):
        main_edit(notes)
    else:
        main_list(notes, identify=args.identify, realpath=args.realpath,
                  filename=args.filename)

if __name__ == "__main__":
    main()
