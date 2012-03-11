import os

from csftp import shelless
from csftp.filepath import FilePath

from zope.interface import implements
from twisted.cred import portal
from twisted.conch.interfaces import ISFTPServer, ISFTPFile
from twisted.python import components
from twisted.conch.ssh import filetransfer
from twisted.conch.ls import lsLine


def _simplifyAttributes(filePath):
    return {"size": filePath.getsize(),
            "uid": filePath.getUserID(),
            "gid": filePath.getGroupID(),
            "permissions": filePath.statinfo.st_mode,
            "atime": filePath.getAccessTime(),
            "mtime": filePath.getModificationTime()}



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
        @raises IOError: if the file does not exist, or is a directory
        """
        fp = self._getFilePath(filename)
        if not (fp.exists() or fp.islink()):  # a broken link does not "exist"
            raise IOError("%s does not exist" % filename)
        if fp.isdir():
            raise IOError("%s is a directory" % filename)
        fp.remove()


    def renameFile(self, oldname, newname):
        """
        Rename the given file/directory/link.

        @param oldpath: the current location of the file/directory/link
        @param newpath: the new location of the file/directory/link
        """
        newFP = self._getFilePath(newname)
        if newFP.exists():
            raise IOError("%s already exists" % newname)
        oldFP = self._getFilePath(oldname)
        if not (oldFP.exists() or oldFP.islink()):
            raise IOError("%s does not exist" % oldname)
        oldFP.moveTo(newFP)


    def makeDirectory(self, path, attrs=None):
        """
        Make a directory.  Ignores the attributes.
        """
        fp = self._getFilePath(path)
        if fp.exists():
            raise IOError("%s already exists." % path)
        fp.createDirectory()


    def removeDirectory(self, path):
        """
        Remove a directory non-recursively.

        @param path: the path of the directory
        @raises IOError: if the directory is not empty or it isn't
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
            raise IOError("%s is not a directory")
        if fp.children():
            raise IOError("%s is not empty.")
        fp.remove()


    def openDirectory(self, path):
        fp = self._getFilePath(path)
        if not fp.isdir():
            raise IOError("%s is not a directory." % path)
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

        @raises IOError: if the path is not a link, or is a link to
        a file/directory outside the root directory
        """
        fp = self._getFilePath(path)
        rp = self._getFilePath(self.realPath(path))
        if fp.exists() and fp != rp:
            return self._getRelativePath(rp)
        raise IOError("%s is not a link." % path)


    def makeLink(self, linkPath, targetPath):
        """
        Create a symbolic link from linkPath to targetPath.

        @raises IOError: if the linkPath already exists, if the
        targetPath does not exist
        """
        lp = self._getFilePath(linkPath)
        tp = self._getFilePath(targetPath)
        if lp.exists():
            raise IOError("%s already exists." % linkPath)
        if not tp.exists():
            raise IOError("%s does not exist." % targetPath)
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
        print 'read'
        self.fd.seek(offset)
        return self.fd.read(length)


    def writeChunk(self, offset, data):
        """
        Write data to the file at the given offset

        @param offset: where to start writing
        @param data: the data to write in the file
        """
        print 'write'
        self.fd.seek(offset)
        self.fd.write(data)


    def getAttrs(self):
        return _simplifyAttributes(self.filePath)


    def setAttrs(self, attrs=None):
        """
        This must return something, in order for certain write to be able to
        happen
        """
        pass
        #raise NotImplementedError



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


components.registerAdapter(ChrootedSFTPServer, ChrootedUser,
                           filetransfer.ISFTPServer)
