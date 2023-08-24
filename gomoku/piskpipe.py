import signal
import subprocess
import logging
import threading
import re
import time
try:
    import queue
except ImportError:
    import Queue as queue

LOGGER = logging.getLogger(__name__)

POLL_TIMEOUT = 5
STOP_TIMEOUT = 2


class TimeoutError(Exception):
    """The piskvork command timed out."""
    pass


class EngineError(Exception):
    """The engine output an error message."""
    pass


class EngineUnknownCommand(Exception):
    """The engine output an unknown command error."""
    pass


class Command(object):
    """Information about the state of a command."""
    def __init__(self):
        self._condition = threading.Condition()
        self._result = None
        self._done = False
        self._done_callbacks = []

    def _invoke_callbacks(self):
        for callback in self._done_callbacks:
            try:
                callback(self)
            except Exception:
                LOGGER.exception("exception calling callback for %r", self)

    def __repr__(self):
        with self._condition:
            if self._done:
                if self._result is None:
                    return "<Command at {0} (finished)>".format(hex(id(self)))
                else:
                    return "<Command at {0} (result={1})>".format(hex(id(self)), self._result)
            else:
                return "<Command at {0} (pending)>".format(hex(id(self)))

    def done(self):
        """Returns whether the command has already been completed."""
        with self._condition:
            return self._done

    def add_done_callback(self, fn):
        """
        Add a callback function to be notified once the command completes.

        The callback function will receive the *Command* object as a single
        argument.

        The callback might be executed on a different thread. If the command
        has already been completed it will be invoked immidiately, instead.
        """
        with self._condition:
            if self._done:
                fn(self)
            else:
                self._done_callbacks.append(fn)

    def result(self, timeout=None):
        """
        Wait for the command to finish and return the result.

        A *timeout* in seconds may be given as a floating point number and
        *TimeoutError* is raised if the command does not complete in time.
        """
        with self._condition:
            if self._done:
                return self._result

            self._condition.wait(timeout)

            if self._done:
                return self._result
            else:
                raise TimeoutError()

    def set_result(self, result):
        with self._condition:
            self._result = result
            self._done = True
            self._condition.notify_all()

        self._invoke_callbacks()

    def execute(self, engine):
        pass


class InfoCommand(Command):
    def __init__(self, options):
        super().__init__()
        self.option_lines = []
        for name, value in options.items():
            self.option_lines.append(f"INFO {name} {value}")

    def execute(self, engine):
        for option_line in self.option_lines:
            engine.send_line(option_line)
        time.sleep(0.05)
        self.set_result(None)


class StartCommand(Command):
    def __init__(self, board_size):
        super().__init__()
        self.board_size = board_size

    def execute(self, engine):
        engine.startok.clear()
        engine.send_line(f"START {self.board_size}")
        engine.startok.wait()
        self.set_result(None)


class BoardCommand(Command):
    def __init__(self, position, start_thinking=True, infinite=False):
        super().__init__()
        self.start_thinking = start_thinking
        self.infinite = infinite
        movestrs = re.findall(r"([a-z][1-9][0-9]?)", position.lower())
        self.moves = [(ord(m[0]) - ord('a'), int(m[1:]) - 1) for m in movestrs]
        self.lines = ["BOARD" if start_thinking else "YXBOARD"]
        color = 1 if len(self.moves) % 2 == 0 else 2
        for move in self.moves:
            self.lines.append(f"{move[0]},{move[1]},{color}")
            color = 3 - color
        self.lines.append("DONE")

    def execute(self, engine):
        if self.start_thinking:
            engine.bestmove = None
            engine.infos = []
            engine.bestmove_received.clear()

        for line in self.lines:
            engine.send_line(line)

        if not self.start_thinking or self.infinite:
            self.set_result(None)
        else:
            engine.bestmove_received.wait()
            self.set_result(engine.bestmove)


class TurnCommand(Command):
    def __init__(self, move):
        super().__init__()
        if isinstance(move, str):
            move = (ord(move[0]) - ord('a'), int(move[1:]) - 1)
        self.moveline = f"TURN {move[0]},{move[1]}"

    def execute(self, engine):
        engine.bestmove = None
        engine.infos = []
        engine.bestmove_received.clear()
        engine.send_line(self.moveline)
        engine.bestmove_received.wait()
        self.set_result(engine.bestmove)


class StopCommand(Command):
    def execute(self, engine):
        if not engine.bestmove_received.is_set():
            engine.send_line("YXSTOP")
        engine.bestmove_received.wait(STOP_TIMEOUT)
        self.set_result(engine.bestmove)


class EndCommand(Command):
    def execute(self, engine):
        engine.send_line("END")
        engine.terminated.wait()
        self.set_result(engine.process.wait_for_return_code())


class TerminationPromise(object):
    def __init__(self, engine):
        self.engine = engine

    def done(self):
        return self.engine.terminated.is_set()

    def result(self, timeout=None):
        self.engine.terminated.wait(timeout)

        if not self.done():
            raise TimeoutError()
        else:
            return self.engine.return_code


class PopenProcess(object):
    def __init__(self, command):
        self.command = command
        self.dead = False
        self._receiving_thread = threading.Thread(target=self._receiving_thread_target)
        self._receiving_thread.daemon = True

    def spawn(self, engine):
        self.engine = engine
        self.process = subprocess.Popen(self.command,
                                        stdout=subprocess.PIPE,
                                        stdin=subprocess.PIPE,
                                        bufsize=1,
                                        universal_newlines=True,
                                        encoding="gb2312")
        self._receiving_thread.start()

    def _receiving_thread_target(self):
        while self.is_alive():
            try:
                line = self.process.stdout.readline()
                if not line:
                    continue

                self.engine.on_line_received(line.rstrip())
            except Exception as e:
                print(f"Error when reading line: {repr(e)}")
                self.dead = True
                break

        self.engine.on_terminated()

    def is_alive(self):
        return self.process.poll() is None

    def terminate(self):
        self.process.terminate()

    def kill(self):
        self.process.kill()

    def close_std_streams(self):
        self.process.stdout.close()
        self.process.stdin.close()

    def send_line(self, string):
        self.process.stdin.write(string)
        self.process.stdin.write("\n")
        self.process.stdin.flush()

    def wait_for_return_code(self):
        self.process.wait()
        return self.process.returncode

    def pid(self):
        return self.process.pid

    def __repr__(self):
        return "<PopenProcess at {0} (pid={1})>".format(hex(id(self)), self.pid())


class SpurProcess(object):
    def __init__(self, shell, command):
        self.shell = shell
        self.command = command

        self._stdout_buffer = []

        self._result = None

        self._waiting_thread = threading.Thread(target=self._waiting_thread_target)
        self._waiting_thread.daemon = True

    def spawn(self, engine):
        self.engine = engine

        self.process = self.shell.spawn(self.command, store_pid=True, allow_error=True, stdout=self)
        self._waiting_thread.start()

    def write(self, byte):
        # Interally called whenever a byte is received.
        if byte == b"\r":
            pass
        elif byte == b"\n":
            self.engine.on_line_received(b"".join(self._stdout_buffer).decode("utf-8"))
            del self._stdout_buffer[:]
        else:
            self._stdout_buffer.append(byte)

    def _waiting_thread_target(self):
        self._result = self.process.wait_for_result()
        self.engine.on_terminated()

    def is_alive(self):
        return self.process.is_running()

    def terminate(self):
        self.process.send_signal(signal.SIGTERM)

    def kill(self):
        self.process.send_signal(signal.SIGKILL)

    def close_std_streams(self):
        # TODO: Spur does not do real clean up.
        #try:
        #    self.process._process_stdin.close()
        #except AttributeError:
        #    self.process._stdin.close()
        #self.process._io._handlers[0]._file_in.close()
        #self.process._io._handlers[1]._file_in.close()
        pass

    def send_line(self, string):
        self.process.stdin_write(string.encode("utf-8"))
        self.process.stdin_write(b"\n")

    def wait_for_return_code(self):
        return self.process.wait_for_result().return_code

    def pid(self):
        return self.process.pid

    def __repr__(self):
        return "<SpurProcess at {0} (pid={1})>".format(hex(id(self)), self.pid())


class Engine(object):
    def __init__(self, process):
        self.process = process
        self.process.spawn(self)
        self.options = dict()
        self.queue = queue.Queue()
        self.startok = threading.Event()
        self.bestmove_received = threading.Event()
        self.terminating = threading.Event()
        self.terminated = threading.Event()
        self.stdin_thread = threading.Thread(target=self._stdin_thread_target)
        self.stdin_thread.daemon = True
        self.return_code = None
        self.bestmove = None
        self.last_error = None
        self.last_unknown = None
        self.infos = []
        self.messages = []
        self.info_handlers = []
        self.message_handlers = []
        self.stdin_thread.start()

    def send_line(self, line):
        LOGGER.debug("%s << %s", self.process, line)
        return self.process.send_line(line)

    def on_line_received(self, buf):
        LOGGER.debug("%s >> %s", self.process, buf)

        command_and_args = buf.split(None, 1)
        if not command_and_args:
            return

        command = command_and_args[0].upper()
        if command == "OK":
            return self._startok()
        elif command == "MESSAGE":
            return self._message(command_and_args[1])
        elif command == "INFO":
            return self._info(command_and_args[1])
        elif command == "ERROR":
            return self._error(command_and_args[1])
        elif command == "DEBUG":
            return self._debug(command_and_args[1])
        elif command == "UNKNOWN":
            return self._unknown(command_and_args[1])
        else:
            return self._bestmove(command)

    def _stdin_thread_target(self):
        while self.is_alive():
            if self.terminating.is_set():
                self.process.kill()
                time.sleep(0.5)
                continue

            try:
                command = self.queue.get(True, POLL_TIMEOUT)
            except queue.Empty:
                continue

            if not self.is_alive():
                break

            command.execute(self)
            self.queue.task_done()

        self.on_terminated()

    def on_terminated(self):
        self.process.close_std_streams()
        self.return_code = self.process.wait_for_return_code()
        self.terminated.set()

    def _startok(self):
        self.startok.set()

    def _bestmove(self, arg):
        moves = [int(coord) for coord in arg.split(',')[:2]]
        self.bestmove = chr(ord('a') + moves[0]) + str(1 + moves[1])
        self.bestmove_received.set()

    def _message(self, arg):
        self.messages.append(arg)
        for handler in self.message_handlers:
            handler(arg)

    def _info(self, arg):
        name, value = arg.split(None, 1)

        def parse_int(token):
            try:
                return int(token)
            except ValueError:
                return None

        if name == 'PV':
            if value == 'DONE':
                for handler in self.info_handlers:
                    handler(self.infos[-1])
                return
            self.infos.append({'pvidx': parse_int(value)})
        elif name == 'NUMPV':
            self.infos[-1]['numpv'] = parse_int(value)
        elif name == 'DEPTH':
            self.infos[-1]['depth'] = parse_int(value)
        elif name == 'SELDEPTH':
            self.infos[-1]['seldepth'] = parse_int(value)
        elif name == 'NODES':
            self.infos[-1]['nodes'] = parse_int(value)
        elif name == 'TOTALNODES':
            self.infos[-1]['totalnodes'] = parse_int(value)
        elif name == 'TOTALTIME':
            self.infos[-1]['totaltime'] = parse_int(value)
        elif name == 'SPEED':
            self.infos[-1]['speed'] = parse_int(value)
        elif name == 'EVAL':
            if value.startswith('+M'):
                self.infos[-1]['mate'] = parse_int(value[2:])
                self.infos[-1]['eval'] = None
            elif value.startswith('-M'):
                self.infos[-1]['mate'] = -parse_int(value[2:])
                self.infos[-1]['eval'] = None
            else:
                self.infos[-1]['mate'] = 0
                self.infos[-1]['eval'] = parse_int(value)
        elif name == 'WINRATE':
            self.infos[-1]['winrate'] = float(value)
        elif name == 'BESTLINE':
            self.infos[-1]['bestline'] = value.strip().lower().split(' ')

    def _error(self, arg):
        self.last_error = arg
        self.startok.set()
        self.bestmove_received.set()
        raise EngineError(arg)

    def _debug(self, arg):
        pass

    def _unknown(self, arg):
        self.last_unknown = arg
        self.startok.set()
        self.bestmove_received.set()
        raise EngineUnknownCommand(arg)

    def _queue_command(self, command, async_callback=None):
        if self.terminated.is_set():
            raise RuntimeError('can not queue command for terminated piskpipe engine')

        self.queue.put(command)

        if async_callback is True:
            return command
        elif isinstance(async_callback, float):
            return command.result(timeout=async_callback)
        elif async_callback:
            command.add_done_callback(async_callback)
            return command
        else:
            return command.result()

    def info(self, options, async_callback=None):
        """
        Set a values for the engines available options.
        :param options: A dictionary with option names as keys.
        :return: Nothing
        """
        return self._queue_command(InfoCommand(options), async_callback)

    def start(self, board_size, async_callback=None):
        """
        Tell the engine that the next search will be from a different game.
        :param board_size: The size of the board.
        :return: Nothing
        """
        return self._queue_command(StartCommand(board_size), async_callback)

    def board(self, position, start_thinking=True, infinite=False, async_callback=None):
        """
        Set up a given position and optionally starts thinking. 
        If the position is from a new game it is recommended to use 
        the *start* command before the *board* command.
        :param position: A position string, eg 'h8h7j6'.
        :param start_thinking: If true, start thinking after send board position.
        :param infinite: Search in the backgorund until a *stop* command is received.
        :return: **In normal search mode** the best move from the engine. 
            **In infinite search mode** or **No thinking** there is no result. See *stop*.
        """
        return self._queue_command(BoardCommand(position, start_thinking, infinite), async_callback)

    def turn(self, move, async_callback=None):
        """
        Make a move on the board.
        :param move: A move string 'h8' or a move coordinates pair (7,7).
        :return: Nothing
        """
        return self._queue_command(TurnCommand(move), async_callback)

    def stop(self, async_callback=None):
        """
        Stop calculating as soon as possible.
        :return: The latest best move. See the *board* command. 
            Results of infinite searches will also be available here.
        """
        return self._queue_command(StopCommand(), async_callback)

    def end(self, async_callback=None):
        """
        Quit the engine as soon as possible.
        :return: The return code of the engine process.
        """
        return self._queue_command(EndCommand(), async_callback)

    def terminate(self, _async=False):
        """
        Terminate the engine.
        This is not a command. It instead tries to terminate the engine
        on operating system level, for example by sending SIGTERM on Unix
        systems. If possible, first try the *end* command.
        :return: The return code of the engine process.
        """
        # self.process.close_std_streams()  # This seems to hang
        self.process.terminate()
        self.terminating.set()

        promise = TerminationPromise(self)
        if _async:
            return promise
        else:
            return promise.result()

    def kill(self, _async=False):
        """
        Kill the engine.
        Forcefully kill the engine process, for example by sending SIGKILL.
        :return: The return code of the engine process.
        """
        # self.process.close_std_streams()  # This seems to hang
        self.process.kill()
        self.terminating.set()

        promise = TerminationPromise(self)
        if _async:
            return promise
        else:
            return promise.result()

    def is_alive(self):
        """Poll the engine process to check if it is alive."""
        return self.process.is_alive()

    def clear_messages(self):
        """Clear the last error and messages."""
        self.last_error = None
        self.last_unknown = None
        self.messages = []


def popen_engine(command, engine_cls=Engine):
    """
    Opens a local gomoku engine process.
    No initialization commands are sent.
    The input and input streams will be linebuffered and able both Windows
    and Unix newlines.
    """
    process = PopenProcess(command)
    return engine_cls(process)


def spur_spawn_engine(shell, command, engine_cls=Engine):
    """
    Spwans a remote engine using a `Spur`_ shell.

    >>> import spur
    >>> shell = spur.SshShell(hostname="localhost", username="username", password="pw")
    >>> engine = chess.uci.spur_spwan_engine(shell, ["/usr/games/stockfish"])
    >>> engine.uci()

    .. _Spur: https://pypi.python.org/pypi/spur
    """
    process = SpurProcess(shell, command)
    return engine_cls(process)
