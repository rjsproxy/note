import re

class NoteAttribute:
    """ Abstraction for note attributes.

        An attribute is a (key, value) tuple with both being strings.  There
        are two special cases: (1) keys beginning with underscores are intended
        for internal/defined use; (2) keys beginning with a dot are used by the
        CLI to select filename extensions and should never be saved.
    """

    def __init__(self, key=None, value=None):
        self.key = key
        self.value = value

    def __repr__(self):
        return "NoteAttribute(\"%s\", \"%s\")" % (self.key, self.value)

    def __str__(self):
        result = str(self.key)
        if self.value:
            result += '=' + str(self.value)
        return result

    @staticmethod
    def decode(attr):
        """ Convert a string into a NoteAttribute. """
        match = re.match(r'(?P<key>[^=]+)(=(?P<value>.+))?', attr)
        if not match:
            raise ArgumentTypeError("Bad NoteAttribute syntax \"%s\"" % name)
        key = match.group('key').strip()
        value = match.group('value')
        if value:
            value = value.strip()
        return NoteAttribute(key, value)

