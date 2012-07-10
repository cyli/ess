import os

from twisted.conch.ssh import filetransfer
from twisted.trial import unittest

from ess import essftp, filepath
from ess.test.test_shelless import execCommand, TestSecured


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

        self.tempdir = filepath.FilePath(self.mktemp())
        self.rootdir = self.tempdir.child("root")
        self.rootdir.child("subdir").makedirs()
        altdir = self.tempdir.child("alt")
        altdir.makedirs()

        altdir.linkTo(self.rootdir.child("altlink"))

        makeFile(self.rootdir.child("fileRoot"))
        self.rootdir.child("fileRoot").linkTo(
            self.rootdir.child("fileRootLink"))
        makeFile(altdir.child("fileAlt"))
        altdir.child("fileAlt").linkTo(self.rootdir.child("fileAltLink"))

        self.server = essftp.EssFTPServer(TestAvatar(self.rootdir.path))


class TestEssFTPServer(TestChrooted, unittest.TestCase):

    def test_getFilePath(self):
        """
        Verify thet _getFilePath won't return a path that is an ancestor of
        the root directory.  (Cheating here because these files and
        directories don't have to exist.)
        """
        for p in (".", "../", "/.//../"):  # these should be the same as root
            self.assertEquals(self.server.root, self.server._getFilePath(p))
        for p in ("0", "/0", "../../0", "0/1/../"):  # these should be 0
            self.assertEquals(self.server.root.child("0"),
                              self.server._getFilePath(p))

    def test_getRelativePath(self):
        """
        Verify that _getRelativePath will return a path relative to the root
        """
        mappings = [("/", self.rootdir),
                    ("/subdir", self.rootdir.child("subdir")),
                    ("/altlink", self.rootdir.child("altlink"))]
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
            (self.rootdir.child("altlink"),
                self.rootdir.child("altlink"),
                "realpath should not reveal ancestors/siblings of root"),
            (self.rootdir.child("fileRoot"),
                self.rootdir.child("fileRoot"),
                "realpath of an actual file should return self"),
            (self.rootdir.child("fileRootLink"),
                self.rootdir.child("fileRoot"),
                "if target is within root, returns the true path"),
            (self.rootdir.child("fileAltLink"),
                self.rootdir.child("fileAltLink"),
                "cannot reveal ancestor/siblings of root")
            ]
        for link, target, msg in linkTargets:
            self.assertEquals(
                self.server.realPath(
                    "/".join(link.segmentsFrom(self.rootdir))),
                "/" + "/".join(target.segmentsFrom(self.rootdir)),
                msg)

    def testReadLink(self):
        """
        Verify that readLink will fail when the path passed is not a link,
        does not exist, or is a pretend directory (a link to a directory
        outside the root directory).
        """
        for failureCase in ("fileRoot", "subdir", "fileAltLink"):
            self.assertRaises(IOError, self.server.readLink, failureCase)
        self.assertEquals(self.server.readLink("fileRootLink"), "/fileRoot")

    def testMakeLink(self):
        """
        Verify that makeLink will create a symbolic link when the link
        doesn't exist and the target exists, and fails otherwise.
        """
        self.server.makeLink("fileRootLink2", "fileRoot")
        self.failUnless(self.rootdir.child("fileRootLink2").islink())
        self.assertEquals(self.server.readLink("fileRootLink2"), "/fileRoot")
        for ln, tg in (("fileRootLink", "fileRoot"), ("fakeLink", "fake")):
            self.assertRaises(IOError, self.server.makeLink, ln, tg)

    def testRemoveFile(self):
        """
        Verify that removeFile only removes files and links
        """
        for fp in self.server.root.walk():
            try:
                self.server.removeFile(self.server._getRelativePath(fp))
            except IOError:
                self.failUnless(fp.isdir(), "failure removing " + str(fp))
        self.assertRaises(IOError, self.server.removeFile, "fileRoot")
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
        except IOError:
            self.fail("Removing empty directory failed.")

        failcases = [
            "fileRoot",  # should not remove files
            "fileRootLink",  # should not remove links
            "altlink"]  # should not remove non-empty directories
        for case in failcases:
            self.assertRaises(IOError, self.server.removeDirectory, case)

        for child in self.tempdir.child("alt").children():
            child.remove()
        try:
            self.server.removeDirectory("altlink")
        except IOError:
            self.fail("Removing empty 'fake directory' failed.")

    def testMakeDirectory(self):
        """
        Verify that makeDirectory creates a directory if it doesn't
        already exist
        """
        self.assertRaises(IOError, self.server.makeDirectory,
                          "subdir")
        try:
            self.server.makeDirectory("subdir2")
        except IOError:
            self.fail("Creating a directory failed.")

    def testRenameFile(self):
        """
        Verify that renaming files, links, and directories work
        """
        for oldname in ("fileRoot", "fileRootLink", "subdir", "altlink"):
            try:
                newname = oldname + ".ren"
                self.server.renameFile(oldname, newname)
            except IOError:
                self.fail("renaming file %s failed." % oldname)
            self.failIf(self.server._getFilePath(oldname).exists(),
                        "%s still exists" % oldname)
            newfp = self.server._getFilePath(oldname + ".ren")
            self.failUnless(newfp.exists() or newfp.islink(),
                            "%s does not exist" % (oldname + ".ren"))

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
            self.failUnless(key in fileAttrs)
            self.failUnless(key in linkAttrs)
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
        a file (not directory) fails
        """
        self.assertRaises(IOError, self.server.openDirectory,
                          "fileRoot")
        count = 0
        for path, longname, attrs in self.server.openDirectory("altlink"):
            count += 1
            self.assertEquals(6, len(attrs.keys()))
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
        dirlist = essftp.ChrootedDirectory(self.server, self.rootdir)
        self.assertEquals(len(dirlist.files), len(self.rootdir.children()))
        for path, longname, attrs in dirlist:
            self.failUnless(self.rootdir.child(path).exists())

    def testOpacity(self):
        """
        Make sure that fake directories and files do not seem as such
        """
        dirlist = essftp.ChrootedDirectory(self.server, self.rootdir)
        for path, longname, attrs in dirlist:
            if path in ("altlink", "fileAltLink"):
                self.assertNotEquals(attrs, self.server.getAttrs(path, False))


class TestChrootedFile(TestChrooted, unittest.TestCase):
    """
    Makes sure that a ChrootedFile meets the ISFTPFile interface
    """
    read = filetransfer.FXF_READ
    write = filetransfer.FXF_WRITE
    append = filetransfer.FXF_APPEND
    creat = filetransfer.FXF_CREAT
    trunc = filetransfer.FXF_TRUNC
    excl = filetransfer.FXF_EXCL

    def setUp(self):
        TestChrooted.setUp(self)
        self.sftpf = essftp.ChrootedFile(
            self.rootdir.child("fileRoot"), self.read)
        self.flagTester = self.sftpf.flagTranslator

    def bitIn(self, lookingFor, flags):
        return flags & lookingFor == lookingFor

    def test_flagTranslator_noReadOrWrite(self):
        """
        Make sure that translation without read or write raises an error
        """
        self.assertRaises(ValueError, self.flagTester, self.trunc)

    def test_flagTranslator_readonly(self):
        """
        Make sure that translation of read without write -> read only
        """
        self.assertEquals(self.flagTester(self.read), os.O_RDONLY)
        self.assertTrue(self.bitIn(os.O_RDONLY,
                                   self.flagTester(self.read | self.append)))

    def test_flagTranslator_writeonly(self):
        """
        Make sure that translation of write without read -> write only
        """
        self.assertEquals(self.flagTester(self.write), os.O_WRONLY)
        self.assertTrue(self.bitIn(os.O_WRONLY,
                                   self.flagTester(self.write | self.creat)))

    def test_flagTranslator_readwrite(self):
        """
        Make sure that translation of read + write -> readwrite
        """
        rdwr = self.flagTester(self.read | self.write)
        self.assertEquals(rdwr, os.O_RDWR)
        self.assertFalse(self.bitIn(os.O_WRONLY, rdwr))

    def test_flagTranslator_otherflags(self):
        """
        Make sure that translation of other flags are correct
        """
        mappings = (
            (self.creat, os.O_CREAT),
            (self.excl, os.O_EXCL),
            (self.append, os.O_APPEND),
            (self.trunc, os.O_TRUNC))
        for fflag, osflag in mappings:
            self.assertTrue(
                self.bitIn(osflag, self.flagTester(self.read | fflag)))

    def test_closable(self):
        """
        Make sure it's closable
        """
        try:
            self.sftpf.close()
        except IOError:
            self.fail("Opening/closing ChrootedFile fails")

    def test_readChunk(self):
        """
        Make sure that it's readable
        """
        fp = self.rootdir.child("fileRoot")
        self.assertEquals(self.sftpf.readChunk(0, 10), fp.path[:10])
        self.assertEquals(self.sftpf.readChunk(5, 8), fp.path[5:13])

    def test_writeChunk(self):
        """
        Make sure that it's writable
        """
        fp = self.rootdir.child("fileRoot")
        sftpf = essftp.ChrootedFile(fp, self.read | self.write)
        sftpf.writeChunk(5, "NEWDATA")
        sftpf.close()
        f = fp.open()
        self.assertEquals(f.read(), fp.path[:5] + "NEWDATA" + fp.path[12:])
        f.close()


class TestEssFTP(TestSecured, unittest.TestCase):
    """
    More of an integration test, to see if sftp works
    """
    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)

    def realmFactory(self):
        self.rootdir = filepath.FilePath(self.mktemp())
        self.rootdir.createDirectory()
        return essftp.EssFTPRealm(self.rootdir.path)

    def setUp(self):
        TestSecured.setUp(self)
        for i in range(5):
            fp = self.rootdir.child("file%d" % i)
            fp.create()
            fp.setContent(fp.path)

        options = "-oUserKnownHostsFile=/dev/null -oStrictHostKeyChecking=no"
        execCommand(self.ssht, "sftp %s -oPort=%d localhost" % (
            options, self.port))

    def test_SFTPSubsystemExists(self):
        """
        Make sure it is possible to connect via SFTP and exit without error.
        """
        self.ssht.write('exit')
        self.ssht.finish()
        return self.ssht.deferred

    def _ls_tester(self, path):
        """
        Tests ls
        """
        def compare(data):
            data = data.split("\n", 1)[-1]  # first line is "sftp> ls"
            expected = self.rootdir.children()
            expected.sort()
            got = [filepath.FilePath(file) for file in data.split()]
            got.sort()
            self.assertEquals(len(got), len(expected))
            for i in range(len(got)):
                self.assertEquals(expected[i].basename(), got[i].basename())

        self.ssht.write('ls %s' % path)
        self.ssht.deferred.addCallback(compare)
        self.ssht.finish()
        return self.ssht.deferred

    def test_lsWorks(self):
        """
        Make sure ls works correctly
        """
        return self._ls_tester(".")

    def test_chrooted(self):
        """
        Make sure that it is chrooted by trying to ls the root
        """
        return self._ls_tester("/")
