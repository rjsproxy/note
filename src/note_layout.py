import os

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
               r'^(?P<nnid>[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8})(?P<ext>\.\S+)$']

