import shelless
import os
from zope.interface import implements
from twisted.cred import portal
from twisted.conch.interfaces import ISFTPServer, ISFTPFile
from twisted.python import components, filepath
from twisted.conch.ssh import filetransfer
from twisted.conch.ls import lsLine


def _simplifyAttributes(filePath):
    return {"size": filePath.getsize(),
            "uid": filePath.getUserID(),
            "gid": filePath.getGroupID(),
            "permissions": filePath.statinfo.st_mode,
            "atime": filePath.getAccessTime(),
            "mtime": filePath.getModificationTime()}



class FilePath(filepath.FilePath):

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



class ChrootedFSError(Exception):
    pass



class ChrootedSSHRealm(object):
    """
    A realm that returns a ChrootedUser as an avatar
    """
    implements(portal.IRealm)

    def __init__(self, root):
        self.root = root


    def requestAvatar(self, avatarID, mind, *interfaces):
        user = ChrootedUser(self.root)
        return interfaces[0], user, user.logout



class ChrootedUser(shelless.ShelllessUser):
    """
    A shell-less user that does not answer any global requests.
    """
    def __init__(self, root):
        shelless.ShelllessUser.__init__(self)
        self.subsystemLookup["sftp"] = filetransfer.FileTransferServer
        self.root = root



class ChrootedSFTPServer:
    implements(ISFTPServer)
    """
    A Chrooted SFTP server based on twisted.python.filepath.FilePath.
    This prevents users from connecting to a path above the set root
    path.  It ignores permissions, since everything is executed as
    whatever user the SFTP server is executed as (it does not need to
    be run setuid).
    """

    def __init__(self, avatar):
        self.avatar = avatar
        self.root = FilePath(self.avatar.root)


    def _getFilePath(self, path):
        """
        Takes a string path and returns a FilePath object corresponding
        to the path.  In this case, it will translate the path into one
        relative to the root.

        @param path: the path (as a string) with which to create a FilePath
        """
        fp = FilePath(self.root.path)
        for subpath in path.split("/"):
            if (not subpath or
                 subpath == "." or
                 (subpath == ".." and fp == self.root)):
                continue
            elif subpath == "..":
                fp = fp.parent()
            else:
                fp = fp.child(subpath)
        assert fp.path.startswith(self.root.path)
        return fp


    def _getRelativePath(self, filePath):
        """
        Takes a FilePath and returns a path string relative to the root

        @param filePath: file/directory/link whose relative path should be
        returned
        @raises filepath.InsecurePath: filePath is not in the root directory
        """
        if filePath == self.root:
            return "/"
        return "/" + "/".join(filePath.segmentsFrom(self.root))


    def _islink(self, fp):
        if fp.islink() and fp.realpath().path.startswith(self.root.path):
            return True
        return False


    def gotVersion(self, otherVersion, extData):
        return {}


    def openFile(self, filename, flags, attrs):
        fp = self._getFilePath(filename)
        return ChrootedSFTPFile(fp, flags, attrs)


    def removeFile(self, filename):
        """
        Remove the given file if it is either a file or a symlink.

        @param filename: the filename/path as a string
        @raises ChrootedFSError: if the file does not exist, or is a directory
        """
        fp = self._getFilePath(filename)
        if not (fp.exists() or fp.islink()):  # a broken link does not "exist"
            raise ChrootedFSError("%s does not exist" % filename)
        if fp.isdir():
            raise ChrootedFSError("%s is a directory" % filename)
        fp.remove()


    def renameFile(self, oldname, newname):
        """
        Rename the given file/directory/link.

        @param oldpath: the current location of the file/directory/link
        @param newpath: the new location of the file/directory/link
        """
        newFP = self._getFilePath(newname)
        if newFP.exists():
            raise ChrootedFSError("%s already exists" % newname)
        oldFP = self._getFilePath(oldname)
        if not (oldFP.exists() or oldFP.islink()):
            raise ChrootedFSError("%s does not exist" % oldname)
        oldFP.moveTo(newFP)


    def makeDirectory(self, path, attrs=None):
        """
        Make a directory.  Ignores the attributes.
        """
        fp = self._getFilePath(path)
        if fp.exists():
            raise ChrootedFSError("%s already exists." % path)
        fp.createDirectory()


    def removeDirectory(self, path):
        """
        Remove a directory non-recursively.

        @param path: the path of the directory
        @raises ChrootedFSError: if the directory is not empty or it isn't
        is a directory
        """
        # The problem comes when path is a link that points to a directory:
        # 1) If the target is a directory in the root directory, and said
        #    directory is empty, the link should not be removed because it
        #    is a link.
        # 2) If the target is a directory outside the root directory, then
        #    the user should not really be able to tell.
        fp = self._getFilePath(path)
        if (not fp.isdir()) or self._islink(fp):
            raise ChrootedFSError("%s is not a directory")
        if fp.children():
            raise ChrootedFSError("%s is not empty.")
        fp.remove()


    def openDirectory(self, path):
        fp = self._getFilePath(path)
        if not fp.isdir():
            raise ChrootedFSError("%s is not a directory." % path)
        return ChrootedDirectory(self, fp)


    def getAttrs(self, path, followLinks=True):
        """
        Get attributes of the path.

        @param path: the path for which attribute are to be gotten
        @param followLinks: if false, then does not return the attributes
        of the target of a link, but rather the link
        """
        fp = self._getFilePath(path)
        fp.restat(followLink=followLinks)
        return _simplifyAttributes(fp)


    def setAttrs(self, path, attrs):
        raise NotImplementedError


    def readLink(self, path):
        """
        Returns the target of a symbolic link (relative to the root), so
        long as the target is within the root directory.  If path is not
        a link, raise an error (or is a link to a file or directory
        outside the root directory, in which case no it will also raise
        an error because no indication should be given that there are any
        files outside the root directory).

        @raises ChrootedFSError: if the path is not a link, or is a link to
        a file/directory outside the root directory
        """
        fp = self._getFilePath(path)
        rp = self._getFilePath(self.realPath(path))
        if fp.exists() and fp != rp:
            return self._getRelativePath(rp)
        raise ChrootedFSError("%s is not a link." % path)


    def makeLink(self, linkPath, targetPath):
        """
        Create a symbolic link from linkPath to targetPath.

        @raises ChrootedFSError: if the linkPath already exists, if the
        targetPath does not exist
        """
        lp = self._getFilePath(linkPath)
        tp = self._getFilePath(targetPath)
        if lp.exists():
            raise ChrootedFSError("%s already exists." % linkPath)
        if not tp.exists():
            raise ChrootedFSError("%s does not exist." % targetPath)
        tp.linkTo(lp)


    def realPath(self, path):
        """
        Despite what the interface says, this function will only return
        the path relative to the root.  However, if it is a link, it will
        return the target of the link rather than the link.  Absolute paths
        will be treated as if they were relative to the root.

        @param path: the path (as a string) to be converted into a string
        """
        fp = self._getFilePath(path)
        if self._islink(fp=fp):
            fp = fp.realpath()
        return self._getRelativePath(fp)


    def extendedRequest(self, extendedName, extendedData):
        raise NotImplementedError


components.registerAdapter(ChrootedSFTPServer, ChrootedUser,
                           filetransfer.ISFTPServer)


#Figure out a way to test this
class ChrootedDirectory:
    """
    A Chrooted SFTP directory based on twisted.python.filepath.FilePath.  It
    does not expose uid and gid, and hides the fact that "fake directories"
    and "fake files" are links.
    """
    def __init__(self, server, filePath):
        """
        @param filePath: The filePath of the directory.  If filePath references
        a file or link to a file, will fail with an UnlistableError (from
        twisted.python.filepath)
        """
        self.server = server
        self.files = filePath.children()


    def __iter__(self):
        return self


    def has_next(self):
        return len(self.files) > 0


    def next(self):
        # TODO: problem - what if the user that logs in is not a user in the
        # system?
        if not self.files:
            raise StopIteration
        f = self.files.pop(0)
        followLink = False
        if not self.server._islink(f):
            #prevents fake directories and files from showing up as links
            followLink = True
        f.restat(followLink=followLink)
        longname = lsLine(f.basename(), f.statinfo)
        longname = longname[:15] + longname[32:]  # remove uid and gid
        return (f.basename(), longname, _simplifyAttributes(f))


    def close(self):
        self.files = None



class ChrootedSFTPFile:
    """
    A Chrooted SFTP file based on twisted.python.filepath.FilePath.
    """
    implements(ISFTPFile)

    def __init__(self, filePath, flags, attrs=None):
        """
        @param filePath: a FilePath to open
        @param flags: flags to open the file with
        """
        self.filePath = filePath
        self.fd = self.filePath.open(flags=self.flagTranslator(flags))


    def flagTranslator(self, flags):
        """
        Translate filetransfer flags to Python file opening modes
        @param flags: flags to translate into file opening mode
        """
        def isInFlags(lookingFor):
            return flags & lookingFor == lookingFor
        # file flags:
        # READ - read to a file
        # WRITE - write to a file
        # APPEND - move seek pointer to end of file (for writing)
        # CREATE - if a file does not exist, create it - nothing otherwise
        # TRUNCATE - resets length of file to zero and discards all old data
        # EXCLUDE - if the file exists, fail to open it
        # TEXT - open in text mode
        # BINARY - open in binary mode

        if isInFlags(filetransfer.FXF_READ):
            if isInFlags(filetransfer.FXF_WRITE):
                newflags = os.O_RDWR
            else:
                newflags = os.O_RDONLY
        elif isInFlags(filetransfer.FXF_WRITE):
            newflags = os.O_WRONLY
        else:
            raise ValueError("Must have read flag, write flag, or both.")

        mappings = ((filetransfer.FXF_CREAT, os.O_CREAT),
                    (filetransfer.FXF_EXCL, os.O_EXCL),
                    (filetransfer.FXF_APPEND, os.O_APPEND),
                    (filetransfer.FXF_TRUNC, os.O_TRUNC))
        for fflag, osflag in mappings:
            if isInFlags(fflag):
                newflags = newflags | osflag

        return newflags


    def close(self):
        self.fd.close()


    def readChunk(self, offset, length):
        """
        Read a chunk of data from the file

        @param offset: where to start reading
        @param length: how much data to read
        """
        self.fd.seek(offset)
        return self.fd.read(length)


    def writeChunk(self, offset, data):
        """
        Write data to the file at the given offset

        @param offset: where to start writing
        @param data: the data to write in the file
        """
        self.fd.seek(offset)
        self.fd.write(data)


    def getAttrs(self):
        raise NotImplementedError


    def setAttrs(self, attrs=None):
        raise NotImplementedError
