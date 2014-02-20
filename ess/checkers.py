"""
Module that provides a SSH public key checker, but without depending
necessarily on pwd
"""
try:
    import pwd as _pwd
except ImportError:
    _pwd = None

from zope.interface import implementer, Interface

from twisted.conch.error import ValidPublicKey
from twisted.conch.ssh.keys import Key
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import ISSHPrivateKey
from twisted.cred.error import UnauthorizedLogin
from twisted.internet import defer
from twisted.python import log
from twisted.python.util import runAsEffectiveUser
from twisted.python.filepath import FilePath


class IAuthorizedKeysDB(Interface):
    """
    An object that provides valid authorized ssh keys mapped to usernames
    """
    def getAuthorizedKeys(username):
        """
        @param username: C{str} username of the user

        @return: an iterable of L{twisted.conch.ssh.keys.Key}
        """


def readAuthorizedKeyFile(fileobj, parsekey=Key.fromString):
    """
    Reads keys from an authorized keys file

    @param fileobj: an open file object which can be read from
    @param parsekey: a callable that takes a string and returns a
        L{twisted.conch.ssh.keys.Key}, mainly to be used for testing.  The
        default is L{twisted.conch.keys.Key.fromString}

    @return: an iterable of L{twisted.conch.ssh.keys.Key}
    """
    for line in fileobj:
        line = line.strip()
        if line and not line.startswith('#'):  # for comments
            try:
                yield parsekey(line)
            except:
                pass


@implementer(IAuthorizedKeysDB)
class AuthorizedKeysFilesMapping(object):
    """
    Object that provides SSH public keys based on a dictionary of usernames
    mapped to authorized key files

    @ivar mapping: C{dict} of usernames mapped to iterables of authorized key
        files
    @ivar parsekey: a callable that takes a string and returns a
        L{twisted.conch.ssh.keys.Key}, mainly to be used for testing.  The
        default is L{twisted.conch.keys.Key.fromString}
    """
    def __init__(self, mapping, parsekey=Key.fromString):
        self.mapping = mapping
        self.parsekey = parsekey

    def getAuthorizedKeys(self, username):
        """
        @see: L{ess.checkers.ISSHPublicKeyDB}
        """
        for fp in (FilePath(f) for f in self.mapping.get(username, [])):
            if fp.exists():
                try:
                    f = fp.open()
                except:
                    log.msg("Unable to read {0}".format(fp.path))
                else:
                    for key in readAuthorizedKeyFile(f, self.parsekey):
                        yield key


@implementer(IAuthorizedKeysDB)
class UNIXAuthorizedKeysFiles(object):
    """
    Object that provides SSH public keys based on public keys listed in
    authorized_keys and authorized_keys2 files in UNIX user .ssh/ directories.

    @ivar pwd: access to the Unix user account and password database (default
        is the Python module L{pwd})
    @ivar runas: a callable that takes a uid, a gid, and a param callable plus
        its args and kwargs, which calls the param callable as the user with
        the given uid and gid - this is mainly to be used for testing.  The
        default is L{twisted.python.util.runAsEffectiveUser}
    @ivar parsekey: a callable that takes a string and returns a
        L{twisted.conch.ssh.keys.Key}, mainly to be used for testing.  The
        default is L{twisted.conch.keys.Key.fromString}
    """
    def __init__(self, pwd=None, runas=runAsEffectiveUser,
                 parsekey=Key.fromString):
        self.pwd = pwd
        self.runas = runas
        self.parsekey = parsekey
        if pwd is None:
            self.pwd = _pwd

    def getAuthorizedKeys(self, username):
        """
        @see: L{ess.checkers.ISSHPublicKeyDB}
        """
        try:
            passwd = self.pwd.getpwnam(username)
        except:
            return

        root = FilePath(passwd.pw_dir).child('.ssh')
        files = ['authorized_keys', 'authorized_keys2']
        for fp in (root.child(f) for f in files):
            if fp.exists():
                f = None
                try:
                    f = fp.open()
                except IOError:
                    if self.runas:
                        f = self.runas(passwd.pw_uid, passwd.pw_gid, fp.open)

                if f is not None:
                    for key in readAuthorizedKeyFile(f, self.parsekey):
                        yield key


@implementer(ICredentialsChecker)
class SSHPublicKeyChecker(object):
    """
    Checker that authenticates SSH public keys, based on public keys listed in
    authorized_keys and authorized_keys2 files in user .ssh/ directories.

    Providing this checker with a L{UNIXAuthorizedKeysFiles} should be
    equivalent to L{twisted.conch.checkers.SSHPublicKeyDatabase}.

    @ivar keydb: a provider of L{ISSHPublicKeyDB}
    """
    credentialInterfaces = (ISSHPrivateKey,)

    def __init__(self, keydb):
        self.keydb = keydb

    def requestAvatarId(self, credentials):
        """
        @see L{twisted.cred.checkers.ICredentialsChecker.requestAvatarId}
        """
        d = defer.maybeDeferred(self._sanityCheckKey, credentials)
        d.addCallback(self._checkKey, credentials)
        d.addCallback(self._verifyKey, credentials)
        return d

    def _sanityCheckKey(self, credentials):
        """
        Check whether the provided credentials are a valid SSH key with a
        signature (does not actually verify the signature)

        @param credentials: The L{ISSHPrivateKey} provider credentials
            offered by the user.

        @raise ValidPublicKey: the credentials do not include a signature. See
            L{error.ValidPublicKey} for more information.

        @raise BadKeyError: the key included with the credentials is not
            recognized as a key

        @return: L{twisted.conch.ssh.keys.Key} of the key in the credentials
        """
        if not credentials.signature:
            raise ValidPublicKey()

        return Key.fromString(credentials.blob)

    def _checkKey(self, pubKey, credentials):
        """
        Check the public key against all authorized keys (if any) for the
        user.

        @param pubKey: L{twisted.conch.ssh.keys.Key} of the key in the
            credentials (just to prevent it from having to be calculated
            again)

        @param credentials: The L{ISSHPrivateKey} provider credentials
            offered by the user.

        @raise UnauthorizedLogin: if the key is not authorized, or if there
            was any error obtaining a list of authorized keys for the user

        @return: The C{pubKey}, if the key is authorized
        """
        try:
            if any(key == pubKey for key in
                   self.keydb.getAuthorizedKeys(credentials.username)):
                return pubKey
        except:
            log.err()
            raise UnauthorizedLogin("Unable to get avatar id")

        raise UnauthorizedLogin("Key not authorized")

    def _verifyKey(self, pubKey, credentials):
        """
        Check whether the credentials themselves are valid, now that we know
        if the key matches the user.

        @param pubKey: L{twisted.conch.ssh.keys.Key} of the key in the
            credentials (just to prevent it from having to be calculated
            again)

        @param credentials: The L{ISSHPrivateKey} provider credentials
            offered by the user.

        @raise UnauthorizedLogin: if the key signature is invalid or there
            was any error verifying the signature

        @return: The user's username, if authentication was successful.
        """
        try:
            if pubKey.verify(credentials.signature, credentials.sigData):
                return credentials.username
        except:  # any error should be treated as a failed login
            log.err()
            raise UnauthorizedLogin('Error while verifying key')

        raise UnauthorizedLogin("Key signature invalid.")
