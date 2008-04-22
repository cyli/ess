import csftp
from test_shelless import execCommand, TestSecured, TesterError
import os
from twisted.trial import unittest
#from twisted.python.filepath import FilePath
from csftp import FilePath
from twisted.test import test_paths
from twisted.conch.ssh import filetransfer

class TestFilePath(test_paths.FilePathTestCase): 
    
    def setUp(self):
        test_paths.FilePathTestCase.setUp(self)
        os.symlink(self.path.child("sub1").path, self._mkpath("sub1.link"))
        os.symlink(self.path.child("sub1").child("file2").path,
                   self._mkpath("file2.link"))
        self.all.sort()

    def test_walk(self): # isn't a replacement exactly
        self.path = csftp.FilePath(self.path.path)
        test_paths.FilePathTestCase.test_walk(self)

    def testRealpath(self):
        """
        Verify that a symlink is correctly normalized
        """
        self.path = csftp.FilePath(self.path.path)
        self.assertEquals(self.path.child("sub1.link").realpath(),
                          self.path.child("sub1"))
        self.assertEquals(self.path.child("sub1").realpath(),
                          self.path.child("sub1"))

    def testSymlink(self):
        """
        Verify that symlink creates a valid symlink that is both a link and
        a file if its target is a file, or a directory if its target is a 
        directory.

        NOTE - should check the listable tests to make sure that they can
        list symlinks correctly.
        """
        self.path = csftp.FilePath(self.path.path)
        srcDsts = [ 
            ( self.path.child("sub2"), self.path.child("sub2.link") ), 
            ( self.path.child("sub2").child("file3.ext1"), 
              self.path.child("file3.ext1.link") )
            ]
        for src, dst in srcDsts:
            src.symlink(dst)
            self.failUnless(dst.islink(), "This is a link")
            self.assertEquals(dst.isdir(), src.isdir())
            self.assertEquals(dst.isfile(), src.isfile())

    def testStatCache(self):
        self.path = csftp.FilePath(self.path.path)
        test_paths.FilePathTestCase.testStatCache(self)
        sub = self.path.child("sub1")
        sublink = self.path.child("sub1.link")
        sub.restat()
        sublink.restat(followLink=False)
        self.assertNotEquals(sub.statinfo, sublink.statinfo)
        sublink.restat()
        self.assertEquals(sub.statinfo, sublink.statinfo)
        sub.restat(followLink=False)
        self.assertEquals(sub.statinfo, sublink.statinfo)


class TestAvatar:
    def __init__(self, root):
        self.root = root


class TestChrooted:

    def setUp(self):
        """
        Creates the following file directory structure:

        <tempdirectory> / : /root : /root/fileRoot <file>
                                  : /root/fileRootLink -> /root/fileRoot
                                  : /root/fileAltLink -> /alt/fileAlt
                                  : /root/subdir <directory>
                          : /alt  : /alt/fileAlt <file>
        """

        def makeFile(fp):
            fp.create()
            fp.setContent(fp.path)

        self.tempdir = FilePath(self.mktemp())
        self.rootdir = self.tempdir.child("root")
        self.rootdir.child("subdir").makedirs()
        altdir = self.tempdir.child("alt")
        altdir.makedirs()

        altdir.symlink(self.rootdir.child("altlink"))

        makeFile(self.rootdir.child("fileRoot"))
        self.rootdir.child("fileRoot").symlink(
            self.rootdir.child("fileRootLink"))
        makeFile(altdir.child("fileAlt"))
        altdir.child("fileAlt").symlink(self.rootdir.child("fileAltLink"))

        self.server = csftp.ChrootedSFTPServer(TestAvatar(self.rootdir.path))


class TestChrootedSFTPServer(TestChrooted, unittest.TestCase):
    
    def test_getFilePath(self):
        """
        Verify thet _getFilePath won't return a path that is an ancestor of
        the root directory.  (Cheating here because these files and
        directories don't have to exist.)
        """
        for p in (".", "../", "/.//../"): # these should be the same as root
            self.assertEquals(self.server.root, self.server._getFilePath(p))
        for p in ("0", "/0", "../../0", "0/1/../"): # these should be 0
            self.assertEquals(self.server.root.child("0"),
                              self.server._getFilePath(p))

    def test_getRelativePath(self):
        """
        Verify that _getRelativePath will return a path relative to the root
        """
        mappings = [ ( "/", self.rootdir ),
                     ( "/subdir", self.rootdir.child("subdir") ),
                     ( "/altlink", self.rootdir.child("altlink") ) ]
        for expected, subject in mappings:
            self.assertEquals(self.server._getRelativePath(subject), expected)

    def test_islink(self):
        """
        Verify that _islink returns false if it's a fake directory, that is,
        a link that points to a directory outside root (since to the user
        it should look like just a directory).
        """

        self.failUnless(self.server._islink(
                self.server._getFilePath("fileRootLink")))
        self.failIf(self.server._islink(self.server._getFilePath("altlink")))

    def testRealPath(self):
        """
        Verify that realpath will normalize a symlink iff the target of the
        symlink is not an ancestor of the root directory.
        """
        linkTargets = [
            ( self.rootdir.child("altlink"),
              self.rootdir.child("altlink"),
              "realpath should not reveal ancestors/siblings of root" ),
            ( self.rootdir.child("fileRoot"),
              self.rootdir.child("fileRoot"),
              "realpath of an actual file should return self" ),
            ( self.rootdir.child("fileRootLink"),
              self.rootdir.child("fileRoot"),
              "if target is within root, returns the true path" ),
            ( self.rootdir.child("fileAltLink"),
              self.rootdir.child("fileAltLink"),
              "cannot reveal ancestor/siblings of root" )
            ]
        for link, target, msg in linkTargets:
            self.assertEquals(
                self.server.realPath(
                    "/".join(link.segmentsFrom(self.rootdir))), 
                "/"+"/".join(target.segmentsFrom(self.rootdir)), 
                msg)

    def testReadLink(self):
        """
        Verify that readLink will fail when the path passed is not a link,
        does not exist, or is a pretend directory (a link to a directory 
        outside the root directory).
        """
        for failureCase in ("fileRoot", "subdir", "fileAltLink"):
            self.assertRaises(csftp.ChrootedFSError, self.server.readLink,
                              failureCase)
        self.assertEquals(self.server.readLink("fileRootLink"), "/fileRoot")

    def testMakeLink(self):
        """
        Verify that makeLink will create a symbolic link when the link
        doesn't exist and the target exists, and fails otherwise.
        """
        self.server.makeLink("fileRootLink2", "fileRoot")
        self.failUnless(self.rootdir.child("fileRootLink2").islink())
        self.assertEquals(self.server.readLink("fileRootLink2"), "/fileRoot")
        for ln, tg in ( ("fileRootLink", "fileRoot"), ("fakeLink", "fake") ):
            self.assertRaises(csftp.ChrootedFSError, 
                              self.server.makeLink, ln, tg)

    def testRemoveFile(self):
        """
        Verify that removeFile only removes files and links
        """
        for fp in self.server.root.walk():
            try:
                self.server.removeFile(self.server._getRelativePath(fp))
            except csftp.ChrootedFSError:
                self.failUnless(fp.isdir(), "failure removing " + str(fp))
        self.assertRaises(csftp.ChrootedFSError, 
                          self.server.removeFile, "fileRoot")
        for fp in self.server.root.walk():
            self.failUnless(fp.isdir())

    def testRemoveDirectory(self):
        """
        Verify that removeDirectory only removes directories if they are
        empty, that it won't remove files or links, and that it will remove
        links if they are "fake directories".
        """
        try:
            self.server.removeDirectory("subdir")
        except csftp.ChrootedFSError:
            self.fail("Removing empty directory failed.")

        failcases = [ "fileRoot",  #should not remove files
                      "fileRootLink", #should not remove links
                      "altlink" ] #should not remove non-empty directories
        for case in failcases:
            self.assertRaises(csftp.ChrootedFSError, 
                              self.server.removeDirectory, case)

        for child in self.tempdir.child("alt").children():
            child.remove()
        try:
            self.server.removeDirectory("altlink")
        except csftp.ChrootedFSError:
            self.fail("Removing empty 'fake directory' failed.")            

    def testMakeDirectory(self):
        """
        Verify that makeDirectory creates a directory if it doesn't
        already exist
        """
        self.assertRaises(csftp.ChrootedFSError, self.server.makeDirectory,
                          "subdir")
        try:
            self.server.makeDirectory("subdir2")
        except csftp.ChrootedFSError:
            self.fail("Creating a directory failed.")

    def testRenameFile(self):
        """
        Verify that renaming files, links, and directories work
        """
        for oldname in ("fileRoot", "fileRootLink", "subdir", "altlink"):
            try:
                newname = oldname + ".ren"
                self.server.renameFile(oldname, newname)
            except csftp.ChrootedFSError:
                self.fail("renaming file %s failed." % oldname)
            self.failIf(self.server._getFilePath(oldname).exists(),
                        "%s still exists" % oldname)
            newfp = self.server._getFilePath(oldname+".ren")
            self.failUnless(newfp.exists() or newfp.islink(),
                            "%s does not exist" % (oldname+".ren"))

    def testGetAttrs(self):
        """
        Since this basically just returns information from FilePath, 
        and FilePath tests cover the statistic-getting functions of
        FilePath, only tests to make sure that the dictionary returned
        is what we expect.
        """
        fileAttrs = self.server.getAttrs("fileRoot")
        linkAttrs = self.server.getAttrs("fileRootLink")
        for key in ["size", "atime", "mtime"]:
            self.failUnless(fileAttrs.has_key(key))
            self.failUnless(linkAttrs.has_key(key))
        self.assertNotEquals(fileAttrs, 
                             self.server.getAttrs("fileRootLink", False))
        self.assertEquals(fileAttrs, linkAttrs)

    def testSetAttrs(self):
        """
        Currently, this is not supported so make sure it raises an error.
        """
        self.assertRaises(NotImplementedError, 
                          self.server.setAttrs, "fileRoot", {})

    def testExtendedRequest(self):
        """
        Not supported
        """
        self.assertRaises(NotImplementedError, self.server.extendedRequest,
                          None, None)

    def testOpenDirectory(self):
        """
        Make sure that what yielded is an iterable, and that trying to open
        a file fails
        """
        self.assertRaises(csftp.ChrootedFSError, self.server.openDirectory,
                          "fileRoot")
        count = 0
        for path, longname, attrs in self.server.openDirectory("altlink"):
            count += 1
            self.assertEquals(4, len(attrs.keys()))
        self.assertEquals(1, count)


class TestChrootedDirectory(TestChrooted, unittest.TestCase):
    """
    Makes sure that a ChrootedDirectory returns an iterable that yields
    the all the children in the directory, and does so without revealing
    anything about files/directories outside of the root directory (by
    revealing links to such files/directories).
    """    
    def testIterable(self):
        """
        Make sure that it is iterable and yields the subdirectory children
        """
        dirlist = csftp.ChrootedDirectory(self.server, self.rootdir)
        self.assertEquals(len(dirlist.files), len(self.rootdir.children()))
        for path, longname, attrs in dirlist:
            self.failUnless(self.rootdir.child(path).exists())

    def testOpacity(self):
        """
        Make sure that fake directories and files do not seem as such
        """
        dirlist = csftp.ChrootedDirectory(self.server, self.rootdir)
        for path, longname, attrs in dirlist:
            if path in ("altlink", "fileAltLink"):
                self.assertNotEquals(attrs, self.server.getAttrs(path, False))


class TestChrootedSFTPFile(TestChrooted, unittest.TestCase):
    """
    Makes sure that a ChrootedSFTPFile meets the ISFTPFile interface
    """
    read = filetransfer.FXF_READ
    write = filetransfer.FXF_WRITE
    append = filetransfer.FXF_APPEND
    creat = filetransfer.FXF_CREAT
    trunc = filetransfer.FXF_TRUNC
    excl = filetransfer.FXF_EXCL

    def testFlagsToModes(self):
        """
        Make sure that it translates file flags to python file modes properly.
        My understanding of the flags is not entirely complete, though, so this
        test suite may not be complete.
        """
        r = self.rootdir
        class TestChrootedSFTPFile(csftp.ChrootedSFTPFile):
            def __init__(self, path):
                self.filePath = r.child(path)
        exists = TestChrootedSFTPFile("fileRoot")
        notexists = TestChrootedSFTPFile("none")

        translates = [ ('r', self.read, exists),
                       ('r+', self.read+self.write, exists),
                       ('a+', self.read+self.write+self.append, exists), 
                       #append pointless w/o write
                       ('w', self.write+self.creat+self.trunc, notexists),
                       ('w', self.write+self.creat+self.trunc, exists),
                       ('a+', self.read+self.write+self.append+self.creat, 
                        notexists),
                       ('a+', self.read+self.write+self.append, exists) ]
        for mode, flags, cfile in translates:
            modes = cfile.flagsToMode(flags)
            self.assertEquals(
                len(modes), 1, 
                "There should only be one mode.  Instead: %s" % str(modes))
            self.assertEquals(mode, modes[0])

        failures = [ (self.read, notexists),
                     (self.creat+self.excl, exists),
                     (self.read+self.write+self.append+self.excl, notexists) ]
        for flags, cfile in failures:
            self.assertRaises(OSError, cfile.flagsToMode, flags)
                       
    def testOpenClosable(self):
        try:
            file = csftp.ChrootedSFTPFile(self.rootdir.child("fileRoot"), 
                                          self.read)
            file.close()
        except csftp.ChrootedFSError:
            self.fail("Opening/closing ChrootedSFTPFile fails")


class TestChrootedSFTP(TestSecured, unittest.TestCase):

    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)
        def produceCSSHR():
            return csftp.ChrootedSSHRealm(os.environ['PWD'])
        self.realmFactory = produceCSSHR

    def testSFTPSubsystemExists(self):
        """
        Make sure it is possible to connect via SFTP and exit without error.
        """
        execCommand(self.ssht, "sftp -oPort=%d localhost" % self.port)
        d = self.ssht.write('exit')
        self.ssht.finish()
        return d
