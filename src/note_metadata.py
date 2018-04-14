class NoteMetadata:
    """ Note Metadata Interface. """

    def __init__(self, filename):
        """ Load metadata from file. """
        self.filename = filename
        try:
            with open(self.filename, 'rb') as metafile:
                self.attr = pickle.load(metafile)
        except:
            # TODO: Metadata needs a version field.
            self.attr = {}

    def save(self):
        """ Write current metadata to disk.

            TODO: Error handling?
        """
        if self.attr:
            with open(self.filename, 'w+b') as metafile:
                pickle.dump(self.attr, metafile)
        else:
            path = Path(self.filename)
            if path.is_file():
                path.unlink()

    def attributes(self):
        """ """
        for key, value in self.attr.items():
            yield NoteAttribute(key,value)

    def select_attribute(self, attr):
        """ Return true if NoteMetada include attr. """
        if attr.key not in self.attr.keys():
            return False
        if attr.value and attr.value != self.attr[attr.key]:
            return False
        return True;

    def remove_attribute(self, attr):
        """ Remove an existing attribute. """
        if self.select_attribute(attr):
            del self.attr[attr.key]

    def assign_attribute(self, attr):
        """ Assign a new attribute. """
        self.attr[attr.key] = attr.value


