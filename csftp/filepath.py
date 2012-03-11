import os

from twisted.python import filepath as fp


class FilePath(fp.FilePath):

    def open(self, mode=None, flags=None):
        """
        Opens self with either a given mode or given flags (such as
        os.O_RDONLY, os.O_CREAT, etc or-ed together - see os module
        documentation).  If both are passed, raises an error.

        If flags are passed, a mode will automatically be generated from
        the flags.  By default, the file will be readable unless os.O_WRONLY
        is passed (without also passing os.O_RDWR - passing os.O_RDONLY also
        will do nothing).  A file will only be writable (appending or
        otherwise) if os.WRONLY or os.RDWR flags are passed.

        @returns: file object to self
        @raises ValueError if both mode and flags are passed
        """
        # User provided flags should not be used with a user given mode because
        # certain combinations of modes and flags will raises very unhelpful
        # "Invalid argument" type errors.  Besides, modes can be generated
        # from the flags given.
        if flags is None:
            if not mode:
                mode = 'r'
            if self.alwaysCreate:
                if 'a' in mode:
                    raise ValueError(
                        "Appending not supported when alwaysCreate == True")
                return self.create()
            return open(self.path, mode + 'b')
        else:
            if mode:
                raise ValueError("Either mode or flags accepted, but not both")

            def isInFlags(lookingFor):
                return flags & lookingFor == lookingFor

            # Given that os.open returns only a file descriptor,
            # FilePath.open returns a file object, a mode must be passed
            # to os.fdopen - this will be determined based on the flags.

            # Modes we care about: 'r', 'w', 'a', 'r+', 'a+'
            # We don't care about w+, because if os.open is called with
            # os.O_CREAT the file will already have been created.  If that
            # flag was not passed, then we don't want the file to be created
            # anyway.

            if isInFlags(os.O_RDWR):
                if isInFlags(os.O_APPEND):
                    mode = 'a+'
                else:
                    mode = 'r+'
            elif isInFlags(os.O_WRONLY):
                if isInFlags(os.O_APPEND):
                    mode = 'a'
                else:
                    mode = 'w'
            else:
                mode = 'r'

            return os.fdopen(os.open(self.path, flags), mode)


    def restat(self, reraise=True, followLink=True):
        try:
            self.statFollowLink = followLink
            statFunc = os.stat
            if not followLink:
                statFunc = os.lstat
            self.statinfo = statFunc(self.path)
        except OSError:
            self.statinfo = 0
            if reraise:
                raise


    def walk(self):
        yield self
        if self.isdir() and not self.islink():
            for c in self.children():
                for subc in c.walk():
                    yield subc


    def realpath(self):
        """
        Returns the real path as a FilePath.  If self is a link, returns the
        a FilePath of the ultimate target (follows all successive links - for
        example, if target is a link, return that link's target and so on).
        If self is not a link, simply returns self.

        This relies on os.path.realpath, which currently claims to work only
        in Unix and Mac but which is defined in Windows.

        Note: os.path.realpath does not resolve links in the middle of paths.
        For instance, given path /x/y/z, if y is a symlink that points to w,
        os.path.realpath (and hence FilePath.realpath) will return /x/y/z
        rather than /x/w/z.

        @return: a FilePath
        """
        return self.clonePath(os.path.realpath(self.path))


FilePath.clonePath = FilePath
