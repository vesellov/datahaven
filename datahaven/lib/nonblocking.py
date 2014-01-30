#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
import os
import sys
import errno
import time
import subprocess
import traceback

PIPE = subprocess.PIPE

#Pipe States:
PIPE_EMPTY = 0
PIPE_READY2READ = 1
PIPE_CLOSED = 2

if subprocess.mswindows:
    from win32file import ReadFile, WriteFile
    from win32pipe import PeekNamedPipe
    from win32api import TerminateProcess, OpenProcess, CloseHandle
    import msvcrt
else:
    import select
    import fcntl
    import signal

class Popen(subprocess.Popen):
    err_report = ''
    def __init__(self, args, bufsize=0, executable=None,
                stdin=None, stdout=None, stderr=None,
                preexec_fn=None, close_fds=False, shell=False,
                cwd=None, env=None, universal_newlines=False,
                startupinfo=None, creationflags=0):

        self.args = args
        subprocess.Popen.__init__(self,
            args, bufsize, executable,
            stdin, stdout, stderr,
            preexec_fn, close_fds, shell,
            cwd, env, universal_newlines,
            startupinfo, creationflags)

    def __del__(self):
        try:
            subprocess.Popen.__del__(self)
        except:
            pass

    def returncode(self):
        return self.returncode

    def recv(self, maxsize=None):
        r = self._recv('stdout', maxsize)
        if r is None:
            return ''
        return r

    def recv_err(self, maxsize=None):
        return self._recv('stderr', maxsize)

    def send_recv(self, input='', maxsize=None):
        return self.send(input), self.recv(maxsize), self.recv_err(maxsize)

    def get_conn_maxsize(self, which, maxsize):
        if maxsize is None:
            maxsize = 1024
        elif maxsize < 1:
            maxsize = 1
        return getattr(self, which), maxsize

    def _close(self, which):
        getattr(self, which).close()
        setattr(self, which, None)

    def state(self):
        return self._state('stdout')

    def make_nonblocking(self):
        if subprocess.mswindows:
            return
        conn, maxsize = self.get_conn_maxsize('stdout', None)
        if conn is None:
            return
        flags = fcntl.fcntl(conn, fcntl.F_GETFL)
        if not conn.closed:
            fcntl.fcntl(conn, fcntl.F_SETFL, flags| os.O_NONBLOCK)

    if subprocess.mswindows:
        def send(self, input):
            if not self.stdin:
                return None

            try:
                x = msvcrt.get_osfhandle(self.stdin.fileno())
                (errCode, written) = WriteFile(x, input)
            except:
                return None

            return written

        def _recv(self, which, maxsize):
            conn, maxsize = self.get_conn_maxsize(which, maxsize)
            if conn is None:
                return None

            try:
                x = msvcrt.get_osfhandle(conn.fileno())
                (read, nAvail, nMessage) = PeekNamedPipe(x, 0)
                if maxsize < nAvail:
                    nAvail = maxsize
                if nAvail > 0:
                    (errCode, read) = ReadFile(x, nAvail, None)
            except:
                return None

            if self.universal_newlines:
                read = self._translate_newlines(read)

            return read

        def _state(self, which):
            conn, maxsize = self.get_conn_maxsize(which, None)
            if conn is None:
                return PIPE_CLOSED
            try:
                x = msvcrt.get_osfhandle(conn.fileno())
            except:
                return PIPE_CLOSED
            try:
                (read, nAvail, nMessage) = PeekNamedPipe(x, 0)
            except:
                return PIPE_CLOSED
            if nAvail > 0:
                return PIPE_READY2READ
            return PIPE_EMPTY

        def kill(self):
            try:
                PROCESS_TERMINATE = 1
                handle = OpenProcess(PROCESS_TERMINATE, False, self.pid)
                TerminateProcess(handle, -1)
                CloseHandle(handle)
            except:
                pass


    else:
        def send(self, input):
            if not self.stdin:
                return None

            if not select.select([], [self.stdin], [], 0)[1]:
                return None

            try:
                written = os.write(self.stdin.fileno(), input)
            except:
                return None

            return written

        def _recv(self, which, maxsize):
            conn, maxsize = self.get_conn_maxsize(which, maxsize)
            if conn is None:
                return None

            flags = fcntl.fcntl(conn, fcntl.F_GETFL)
            if not conn.closed:
                fcntl.fcntl(conn, fcntl.F_SETFL, flags| os.O_NONBLOCK)

            try:
                if not select.select([conn], [], [], 0)[0]:
                    return None

                r = conn.read(maxsize)
                if not r:
                    return None

                if self.universal_newlines:
                    r = self._translate_newlines(r)
                return r
            finally:
                if not conn.closed:
                    fcntl.fcntl(conn, fcntl.F_SETFL, flags)

        def _state(self, which):
            conn, maxsize = self.get_conn_maxsize(which, None)
            if conn is None:
                return PIPE_CLOSED

            try:
                # check and see if there is any input ready
                ready = select.select([conn],[],[], 0)
                if conn in ready[0]:
                    return PIPE_READY2READ
                return PIPE_EMPTY
            except:
                return PIPE_CLOSED

        def kill(self):
            os.kill(self.pid, signal.SIGTERM)



def ExecuteString(execstr):
    try:
        import win32process
        return Popen(
            execstr,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags = win32process.CREATE_NO_WINDOW,)
    except:
        return None
