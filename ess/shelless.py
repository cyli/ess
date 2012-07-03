from twisted.conch.avatar import ConchUser
from twisted.conch.ssh import session
from twisted.cred import portal
from twisted.python import log

from zope import interface


class ShelllessSSHRealm:
    interface.implements(portal.IRealm)

    def requestAvatar(self, avatarID, mind, *interfaces):
        user = ShelllessUser()
        return interfaces[0], user, user.logout


class ShelllessUser(ConchUser):
    """
    A shell-less user that does not answer any global requests.
    """
    def __init__(self, root=None):
        ConchUser.__init__(self)
        self.channelLookup["session"] = ShelllessSession

    def logout(self):
        pass   # nothing to do


class ShelllessSession(session.SSHSession):

    name = 'shellessSession'

    def __init__(self, *args, **kw):
        session.SSHSession.__init__(self, *args, **kw)

    def _noshell(self):
        if not self.closing:
            self.write("This server does not provide shells "
                       "or allow command execution.\n")
            self.loseConnection()
        return 0

    def request_shell(self, data):
        log.msg("shell request rejected")
        return self._noshell()

    def request_exec(self, data):
        log.msg("execution request rejected")
        return self._noshell()

    def request_pty_req(self, data):
        log.msg("pty request rejected")
        return self._noshell()

    def request_window_change(self, data):
        log.msg("window change request rejected")
        return 0
