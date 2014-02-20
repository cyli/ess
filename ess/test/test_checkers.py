"""
Tests for L{ess.checkers}.
"""

from collections import namedtuple
from cStringIO import StringIO

from zope.interface.verify import verifyObject

from twisted.conch.error import ValidPublicKey
from twisted.conch.ssh.keys import BadKeyError
from twisted.cred.credentials import SSHPrivateKey
from twisted.cred.error import UnauthorizedLogin
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from twisted.conch.test.keydata import (publicRSA_openssh, privateRSA_openssh,
                                        publicDSA_openssh, privateDSA_openssh)
from twisted.python.fakepwd import UserDatabase
from twisted.test.test_process import MockOS

from ess.checkers import (readAuthorizedKeyFile, IAuthorizedKeysDB,
                          AuthorizedKeysFilesMapping,
                          UNIXAuthorizedKeysFiles, SSHPublicKeyChecker, Key)


class AuthorizedKeyFileReaderTestCase(TestCase):
    """
    Tests for L{readAuthorizedKeyFile}
    """
    def test_ignores_comments(self):
        """
        L{readAuthorizedKeyFile} does not attempt to turn
        comments into keys
        """
        fileobj = StringIO('# this comment is ignored\n'
                           'this is not\n'
                           '# this is again\n'
                           'and this is not')
        result = readAuthorizedKeyFile(fileobj, lambda x: x)
        self.assertEqual(['this is not', 'and this is not'], list(result))

    def test_ignores_leading_whitespace_and_empty_lines(self):
        """
        L{readAuthorizedKeyFile} ignores leading whitespace in lines, as well
        as empty lines
        """
        fileobj = StringIO("""
                           # ignore
                           not ignored
                           """)
        result = readAuthorizedKeyFile(fileobj, parsekey=lambda x: x)
        self.assertEqual(['not ignored'], list(result))

    def test_returns_ignores_unparsable_keys(self):
        """
        L{readAuthorizedKeyFile} does not raise an exception
        when a key fails to parse, but rather just keeps going
        """
        def fail_on_some(line):
            if line.startswith('f'):
                raise Exception('failed to parse')
            return line

        fileobj = StringIO('failed key\ngood key')
        result = readAuthorizedKeyFile(fileobj,
                                                parsekey=fail_on_some)
        self.assertEqual(['good key'], list(result))


class AuthorizedKeysFilesMappingTestCase(TestCase):
    """
    Tests for L{AuthorizedKeysFilesMapping}
    """
    def setUp(self):
        self.root = FilePath(self.mktemp())
        self.root.makedirs()

        authorized_keys = [self.root.child('key{0}'.format(i))
                           for i in range(2)]
        for i, fp in enumerate(authorized_keys):
            fp.setContent('file {0} key 1\nfile {0} key 2'.format(i))

        self.authorized_paths = [fp.path for fp in authorized_keys]

    def test_implements_interface(self):
        """
        L{AuthorizedKeysFilesMapping} implements L{IAuthorizedKeysDB}
        """
        keydb = AuthorizedKeysFilesMapping({'alice': self.authorized_paths})
        verifyObject(IAuthorizedKeysDB, keydb)

    def test_no_keys_for_unauthorized_user(self):
        """
        If the user is not in the mapping provided to
        L{AuthorizedKeysFilesMapping}, an empty iterator is returned
        by L{AuthorizedKeysFilesMapping.getAuthorizedKeys}
        """
        keydb = AuthorizedKeysFilesMapping({'alice': self.authorized_paths},
                                           lambda x: x)
        self.assertEqual([], list(keydb.getAuthorizedKeys('bob')))

    def test_all_keys_in_all_authorized_files_for_authorized_user(self):
        """
        If the user is in the mapping provided to
        L{AuthorizedKeysFilesMapping}, an iterator with all the keys in all
        the authorized files is returned by
        L{AuthorizedKeysFilesMapping.getAuthorizedKeys}
        """
        keydb = AuthorizedKeysFilesMapping({'alice': self.authorized_paths},
                                           lambda x: x)
        keys = ['file 0 key 1', 'file 0 key 2',
                'file 1 key 1', 'file 1 key 2']
        self.assertEqual(keys, list(keydb.getAuthorizedKeys('alice')))

    def test_ignores_nonexistant_or_unreadable_file(self):
        """
        L{AuthorizedKeysFilesMapping.getAuthorizedKeys} returns only the
        keys in the authorized files named that exist and are readable
        """
        directory = self.root.child('key2')
        directory.makedirs()

        keydb = AuthorizedKeysFilesMapping(
            {'alice': [directory.path,
                       self.root.child('key3').path,
                       self.authorized_paths[0]]},
            lambda x: x)
        self.assertEqual(['file 0 key 1', 'file 0 key 2'],
                         list(keydb.getAuthorizedKeys('alice')))


class UNIXAuthorizedKeysFilesTestCase(TestCase):
    """
    Tests for L{UNIXAuthorizedKeysFiles}
    """
    def setUp(self):
        mockos = MockOS()
        mockos.path = FilePath(self.mktemp())
        mockos.path.makedirs()

        self.userdb = UserDatabase()
        self.userdb.addUser('alice', 'password', 1, 2, 'alice lastname',
                            mockos.path.path, '/bin/shell')

        self.sshDir = mockos.path.child('.ssh')
        self.sshDir.makedirs()
        authorized_keys = self.sshDir.child('authorized_keys')
        authorized_keys.setContent('key 1\nkey 2')

    def test_implements_interface(self):
        """
        L{AuthorizedKeysFilesMapping} implements L{IAuthorizedKeysDB}
        """
        keydb = UNIXAuthorizedKeysFiles(self.userdb)
        verifyObject(IAuthorizedKeysDB, keydb)

    def test_no_keys_for_unauthorized_user(self):
        """
        If the user is not in the user database provided to
        L{UNIXAuthorizedKeysFiles}, an empty iterator is returned
        by L{UNIXAuthorizedKeysFiles.getAuthorizedKeys}
        """
        keydb = UNIXAuthorizedKeysFiles(self.userdb, parsekey=lambda x: x)
        self.assertEqual([], list(keydb.getAuthorizedKeys('bob')))

    def test_all_keys_in_all_authorized_files_for_authorized_user(self):
        """
        If the user is in the user database provided to
        L{UNIXAuthorizedKeysFiles}, an iterator with all the keys in
        C{~/.ssh/authorized_keys} and C{~/.ssh/authorized_keys2} is returned
        by L{UNIXAuthorizedKeysFiles.getAuthorizedKeys}
        """
        self.sshDir.child('authorized_keys2').setContent('key 3')
        keydb = UNIXAuthorizedKeysFiles(self.userdb, parsekey=lambda x: x)
        self.assertEqual(['key 1', 'key 2', 'key 3'],
                         list(keydb.getAuthorizedKeys('alice')))

    def test_ignores_nonexistant_file(self):
        """
        L{AuthorizedKeysFilesMapping.getAuthorizedKeys} returns only the
        keys in C{~/.ssh/authorized_keys} and C{~/.ssh/authorized_keys2} if
        they exist
        """
        keydb = UNIXAuthorizedKeysFiles(self.userdb, parsekey=lambda x: x)
        self.assertEqual(['key 1', 'key 2'],
                         list(keydb.getAuthorizedKeys('alice')))

    def test_ignores_unreadable_file(self):
        """
        L{AuthorizedKeysFilesMapping.getAuthorizedKeys} returns only the
        keys in C{~/.ssh/authorized_keys} and C{~/.ssh/authorized_keys2} if
        they are readable
        """
        self.sshDir.child('authorized_keys2').makedirs()
        keydb = UNIXAuthorizedKeysFiles(self.userdb, parsekey=lambda x: x,
                                        runas=None)
        self.assertEqual(['key 1', 'key 2'],
                         list(keydb.getAuthorizedKeys('alice')))

    def test_opens_unreadable_file_as_user_given_runas(self):
        """
        L{AuthorizedKeysFilesMapping.getAuthorizedKeys}, if unable to read
        an C{authorized_keys} file, will attempt to open it as the user
        """
        self.sshDir.child('authorized_keys2').makedirs()

        def runas(uid, gid, callable):
            self.assertEqual((1, 2), (uid, gid))
            return StringIO('key 3')

        keydb = UNIXAuthorizedKeysFiles(self.userdb, parsekey=lambda x: x,
                                        runas=runas)
        self.assertEqual(['key 1', 'key 2', 'key 3'],
                         list(keydb.getAuthorizedKeys('alice')))


_KeyDB = namedtuple('KeyDB', ['getAuthorizedKeys'])


class _DummyException(Exception):
    pass


class SSHPublicKeyCheckerTestCase(TestCase):
    """
    Tests for L{SSHPublicKeyChecker}
    """
    def setUp(self):
        self.credentials = SSHPrivateKey(
            'alice', 'ssh-rsa', publicRSA_openssh, 'foo',
             Key.fromString(privateRSA_openssh).sign('foo'))
        self.keydb = _KeyDB(lambda _: [Key.fromString(publicRSA_openssh)])
        self.checker = SSHPublicKeyChecker(self.keydb)

    def test_credentials_without_signature(self):
        """
        Calling L{SSHPublicKeyChecker.requestAvatarId} with credentials that
        do not have a signature fails with L{ValidPublicKey}
        """
        self.credentials.signature = None
        self.failureResultOf(self.checker.requestAvatarId(self.credentials),
                             ValidPublicKey)

    def test_credentials_with_bad_key(self):
        """
        Calling L{SSHPublicKeyChecker.requestAvatarId} with credentials that
        have a bad key fails with L{BadKeyError}
        """
        self.credentials.blob = ''
        self.failureResultOf(self.checker.requestAvatarId(self.credentials),
                             BadKeyError)

    def test_failure_getting_authorized_keys(self):
        """
        If L{IAuthorizedKeysDB.getAuthorizedKeys} raises an exception,
        L{SSHPublicKeyChecker.requestAvatarId} fails with L{UnauthorizedLogin}
        """
        def fail(_):
            raise _DummyException()

        self.keydb = _KeyDB(fail)
        self.checker = SSHPublicKeyChecker(self.keydb)
        self.failureResultOf(self.checker.requestAvatarId(self.credentials),
                             UnauthorizedLogin)
        self.flushLoggedErrors(_DummyException)

    def test_credentials_no_matching_key(self):
        """
        If L{IAuthorizedKeysDB.getAuthorizedKeys} returns no keys that match
        the credentials, L{SSHPublicKeyChecker.requestAvatarId} fails with
        L{UnauthorizedLogin}
        """
        self.credentials.blob = publicDSA_openssh
        self.failureResultOf(self.checker.requestAvatarId(self.credentials),
                             UnauthorizedLogin)

    def test_credentials_invalid_signature(self):
        """
        Calling L{SSHPublicKeyChecker.requestAvatarId} with credentials that
        are incorrectly signed fails with L{UnauthorizedLogin}
        """
        self.credentials.signature = (
            Key.fromString(privateDSA_openssh).sign('foo'))
        self.failureResultOf(self.checker.requestAvatarId(self.credentials),
                             UnauthorizedLogin)

    def test_failure_verifying_key(self):
        """
        If L{Key.verify} raises an exception,
        L{SSHPublicKeyChecker.requestAvatarId} fails with L{UnauthorizedLogin}
        """
        def fail(*args, **kwargs):
            raise _DummyException()

        self.patch(Key, 'verify', fail)

        self.failureResultOf(self.checker.requestAvatarId(self.credentials),
                             UnauthorizedLogin)
        self.flushLoggedErrors(_DummyException)

    def test_username_returned_on_success(self):
        """
        L{SSHPublicKeyChecker.requestAvatarId}, if successful, callbacks with
        the username
        """
        d = self.checker.requestAvatarId(self.credentials)
        self.assertEqual('alice', self.successResultOf(d))
