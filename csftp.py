import shelless
import os
from zope import interface
from twisted.cred import portal
from twisted.conch.interfaces import ISFTPServer, ISFTPFile
from twisted.python import log, components, filepath
from twisted.conch.ssh import filetransfer
from twisted.conch.ls import lsLine


def simplifyAttributes(filePath):
    return { "size" : filePath.statinfo.st_size,
             "permissions" : filePath.statinfo.st_mode,
             "atime" : filePath.statinfo.st_mtime,
             "mtime" : filePath.statinfo.st_atime }


class FilePath(filepath.FilePath):

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
 
    def remove(self):
        if self.isdir() and not self.islink():
            for child in self.children():
                child.remove()
            os.rmdir(self.path)
        else:
            os.remove(self.path)
        self.restat(False)

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

    def symlink(self, linkFilePath):
        """
        Creates a symlink to self to at the path in the FilePath
        linkFilePath.  Only works on posix systems due to its dependence on
        os.symlink.

        @param linkFilePath: a FilePath representing the link to be created
        @raise ValueError: If linkFilePath already exists or if the inability 
        to create the symlink is due to the fact that linkFilePath.parent() 
        does not exist.
        """
        if linkFilePath.exists():
            raise ValueError("%s already exists" % linkFilePath.path)
        p = linkFilePath.parent()
        if not p.exists():
            raise ValueError("%s does not exist" % p.path)
        os.symlink(self.path, linkFilePath.path)

FilePath.clonePath = FilePath


class ChrootedFSError(Exception):
    pass


class ChrootedSSHRealm:
    interface.implements(portal.IRealm)

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
    """
    A Chrooted SFTP server based on twisted.python.filepath.FilePath.
    This prevents users from connecting to a path above the set root
    path.  It ignores permissions, since everything is executed as
    whatever user the SFTP server is executed as (it does not need to
    be run setuid).
    """
    
    interface.implements(ISFTPServer)
    
    def __init__(self, avatar):
        self.avatar = avatar
        self.root = FilePath(self.avatar.root)

    def gotVersion(self, otherVersion, extData):
        return {}

    def _getFilePath(self, path):
        """
        Takes a string path and returns a FilePath object corresponding
        to the path.  In this case, it will translate the path into one 
        relative to the root.

        @param path: the path (as a string) with which to create a FilePath
        """
        fp = FilePath(self.root.path)
        for subpath in path.split("/"):
            if ( not subpath or 
                 subpath == "." or 
                 ( subpath == ".." and fp == self.root ) ):
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
        if fp.exists() and fp!=rp:
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
        tp.symlink(lp)

    def removeFile(self, filename):
        """
        Remove the given file if it is either a file or a symlink.

        @param filename: the filename/path as a string
        @raises ChrootedFSError: if the file does not exist, or is a directory
        """
        fp = self._getFilePath(filename)
        if not (fp.exists() or fp.islink()): #a broken link does not "exist"
            raise ChrootedFSError("%s does not exist" % filename)
        if fp.isdir():
            raise ChrootedFSError("%s is a directory" % filename)
        fp.remove()

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

    def makeDirectory(self, path, attrs=None):
        """
        Make a directory.  Ignores the attributes.
        """
        fp = self._getFilePath(path)
        if fp.exists():
            raise ChrootedFSError("%s already exists." % path)
        fp.createDirectory()

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

    def getAttrs(self, path, followLinks=True):
        """
        Get attributes of the path.

        @param path: the path for which attribute are to be gotten
        @param followLinks: if false, then does not return the attributes
        of the target of a link, but rather the link
        """
        fp = self._getFilePath(path)
        fp.restat(followLink=followLinks)
        return simplifyAttributes(fp)
   
    def setAttrs(self, path, attrs):
        raise NotImplementedError

    def extendedRequest(self, extendedName, extendedData):
        raise NotImplementedError

    def openDirectory(self, path):
        fp = self._getFilePath(path)
        if not fp.isdir():
            raise ChrootedFSError("%s is not a directory." % path)
        return ChrootedDirectory(self, fp)
    
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
        return len(self.files)>0

    def next(self):
        if not self.files:
            raise StopIteration
        f = self.files.pop(0)
        followLink = False
        if not self.server._islink(f): 
            #prevents fake directories and files from showing up as links
            followLink = True
        f.restat(followLink=followLink)
        longname = lsLine(f.basename(), f.statinfo)
        longname = longname[:15]+longname[32:]  #remove uid and gid
        return (f.basename(), longname, simplifyAttributes(f))

    def close(self):
        self.files = None


class ChrootedSFTPFile:
    """
    A Chrooted SFTP file based on twisted.python.filepath.FilePath.
    """    
    interface.implements(ISFTPFile)

    def __init__(self, filePath, flags, attrs=None):
        """
        @param filePath: a FilePath to open
        @param flags: flags to open the file with
        """
        self.filePath = filePath
        self.fd = self.filePath.open(self.flagsToMode(flags)[0])

    def flagsToMode(self, flags):
        """
        Translate file flags to Python file opening modes
        @param flags: flags to translate into file opening mode
        @param exists: boolean that says whether the file exists or not
        """
        # Python file access modes:
        # 'r'  - read from file - file should exist or error
        # 'w'  - write to file - overwrites or creates
        # 'a'  - append to file or create file
        # 'r+' - read from and write to file - file should exist or error
        # 'w+' - write to and read form file - overwrites or creates
        # 'a+' - append to and read from file - appends or creates

        # file flags:
        # READ - read to a file
        # WRITE - write to a file
        # APPEND - move seek pointer to end of file (for writing)
        # CREATE - if a file does not exist, create it - nothing otherwise
        # TRUNCATE - resets length of file to zero and discards all old data
        # EXCLUDE - if the file exists, fail to open it
        # TEXT - open in text mode
        # BINARY - open in binary mode
        m = ['r', 'w', 'a', 'r+', 'w+', 'a+']
        if ( flags & filetransfer.FXF_CREAT != filetransfer.FXF_CREAT and
             not self.filePath.exists() ):
            raise OSError("%s does not exist." % self.filePath.path)
        if ( flags & filetransfer.FXF_EXCL == filetransfer.FXF_EXCL and
             self.filePath.exists() ):
            raise OSError("%s exists." % self.filePath.path)
        # read flag
        if flags & filetransfer.FXF_READ != filetransfer.FXF_READ:
            m = filter(lambda x: x.find('r')<0 and x.find('+')<0, m)
        else:
            m = filter(lambda x: x=='r' or x.find('+')>=0, m)
        # write flag
        if flags & filetransfer.FXF_WRITE != filetransfer.FXF_WRITE:
            m = filter(lambda x: x.find('w')<0 and x.find('+')<0, m)
        else:
            m = filter(lambda x: x!='r', m)
        # append flag
        if flags & filetransfer.FXF_APPEND != filetransfer.FXF_APPEND:
            m = filter(lambda x: x.find('a')<0, m)
        else:
            m = filter(lambda x: x.find('a')>=0, m)
        # truncate flag
        if flags & filetransfer.FXF_TRUNC != filetransfer.FXF_TRUNC:
            m = filter(lambda x: x.find('w')<0, m)
        return m

    def close(self):
        self.fd.close()
