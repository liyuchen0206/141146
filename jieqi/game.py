import json
import random


class JieQi:
    def __init__(self, info=None):
        piece_types = ['r', 'a', 'c', 'p', 'n', 'b', 'R', 'A', 'C', 'P', 'N', 'B']
        self.side = 'w'
        self.moves = []
        self.global_dark_pieces = {k: 0 for k in piece_types}
        self.captured_pieces = {
            'w': {'r': 0, 'a': 0, 'c': 0, 'p': 0, 'n': 0, 'b': 0},
            'b': {'R': 0, 'A': 0, 'C': 0, 'P': 0, 'N': 0, 'B': 0}
        }
        moves = []
        if info:
            info = json.loads(info)
            self.board = info['board']
            self.side = info['side']
            moves = info['moves']
        else:
            self.board = self.generate_random_board()
        for row in self.board:
            for piece, visible in row:
                if not visible:
                    self.global_dark_pieces[piece] += 1
        self.start_fen = self.get_fen(self.side)
        # print(self.draw_board_to_str(self.board))
        for move in moves:
            is_capture, flipped_dark, capture_dark = self.make_move(move)
            self.moves.append(move + flipped_dark + capture_dark)

    @staticmethod
    def get_piece_count_str(piece_list):
        return "".join([p + str(c) if c > 0 else '' for p, c in piece_list.items()])

    @staticmethod
    def board_to_str(board):
        fen = ''
        for row in board:
            empty = 0
            for c, state in row:
                if c == '':
                    empty += 1
                else:
                    if empty > 0:
                        fen += str(empty)
                        empty = 0
                    if state:
                        fen += c
                    else:
                        if c.isupper():
                            fen += 'X'
                        else:
                            fen += 'x'
            if empty > 0:
                fen += str(empty)
            fen += '/'
        fen = fen[:-1]
        return fen

    @staticmethod
    def generate_random_board():
        piece_list_lower = ['a', 'b', 'n', 'r', 'c'] * 2 + ['p'] * 5
        piece_list_upper = [x.upper() for x in piece_list_lower]
        random.shuffle(piece_list_lower)
        random.shuffle(piece_list_upper)
        board = [
            ['x', 'x', 'x', 'x', 'k', 'x', 'x', 'x', 'x'],
            ['', '', '', '', '', '', '', '', ''],
            ['', 'x', '', '', '', '', '', 'x', ''],
            ['x', '', 'x', '', 'x', '', 'x', '', 'x'],
            ['', '', '', '', '', '', '', '', ''],
            ['', '', '', '', '', '', '', '', ''],
            ['X', '', 'X', '', 'X', '', 'X', '', 'X'],
            ['', 'X', '', '', '', '', '', 'X', ''],
            ['', '', '', '', '', '', '', '', ''],
            ['X', 'X', 'X', 'X', 'K', 'X', 'X', 'X', 'X']
        ]
        for row in range(10):
            for col in range(9):
                piece = board[row][col]
                if piece == 'x':
                    board[row][col] = (piece_list_lower.pop(), False)
                elif piece == 'X':
                    board[row][col] = (piece_list_upper.pop(), False)
                else:
                    board[row][col] = (piece, True)
        return board

    @staticmethod
    def get_rest_from_str(rest_str):
        rest = {}
        for i in range(0, len(rest_str), 2):
            rest[rest_str[i]] = int(rest_str[i + 1])
        return rest

    @staticmethod
    def generate_random_board_info_from_fen(fen):
        parts = fen.split(' moves ')
        moves = []
        if len(parts) > 1:
            moves = parts[1].split(' ')
            fen = parts[0]
        parts = fen.split(' ')
        rows = parts[0].split('/')
        rest = JieQi.get_rest_from_str(parts[1])
        side = 'b' if parts[2] == 'b' else 'w'
        rest_red = []
        rest_black = []
        for piece in rest:
            if piece.isupper():
                rest_red.extend([piece] * rest[piece])
            else:
                rest_black.extend([piece] * rest[piece])
        random.shuffle(rest_red)
        random.shuffle(rest_black)
        board = []
        for row in rows:
            board_row = []
            for c in row:
                if c.isdigit():
                    board_row += [('', True)] * int(c)
                else:
                    if c in ['k', 'K']:
                        board_row.append((c, True))
                    elif c == 'x':
                        board_row.append((rest_black.pop(), False))
                    elif c == 'X':
                        board_row.append((rest_red.pop(), False))
                    elif c == 'f':
                        board_row.append((rest_black.pop(), True))
                    elif c == 'F':
                        board_row.append((rest_red.pop(), True))
                    else:
                        board_row.append((c, False))
            board.append(board_row)
        return {
            'board': board,
            'side': side,
            'moves': moves
        }

    @staticmethod
    def get_visible_fen(board):
        fen = ''
        for row in board:
            empty = 0
            for c, state in row:
                if c == '':
                    empty += 1
                else:
                    if empty > 0:
                        fen += str(empty)
                        empty = 0
                    fen += c
            if empty > 0:
                fen += str(empty)
            fen += '/'
        fen = fen[:-1]
        return fen + " w"

    @staticmethod
    def fen_to_board(fen: str):
        parts = fen.split(' ')
        rows = parts[0].split('/')
        board = []
        for row in rows:
            board_row = []
            for c in row:
                if c.isdigit():
                    board_row += [('', True)] * int(c)
                else:
                    if c in ['k', 'K']:
                        board_row.append((c, True))
                    else:
                        board_row.append((c, False))
            board.append(board_row)
        return board

    @staticmethod
    def pgn_to_cord(pos_str: str):
        row = 9 - int(pos_str[1])
        col = ord(pos_str[0]) - ord('a')
        return row, col

    @staticmethod
    def pgn_to_vec(move_str: str):
        from_pos = JieQi.pgn_to_cord(move_str[:2])
        to_pos = JieQi.pgn_to_cord(move_str[2:4])
        return from_pos, to_pos

    def make_move(self, move_str):
        from_pos, to_pos = JieQi.pgn_to_vec(move_str)
        target_piece, target_visible = self.board[to_pos[0]][to_pos[1]]
        from_piece, from_visible = self.board[from_pos[0]][from_pos[1]]
        eat_piece = True if target_piece != '' else False
        if not from_piece:
            raise Exception('No piece at from position')
        if target_piece and self.get_piece_side(from_piece) == self.get_piece_side(target_piece):
            raise Exception(f'Invalid move {move_str}, '
                            f'the target piece {target_piece} is the same side as the from piece {from_piece}')
        if not target_visible:
            self.captured_pieces[self.get_piece_side(from_piece)][target_piece] += 1
        if not from_visible:
            self.global_dark_pieces[from_piece] -= 1
        self.board[to_pos[0]][to_pos[1]] = (from_piece, True)
        self.board[from_pos[0]][from_pos[1]] = ('', True)
        # print(move_str)
        # print(self.draw_board_to_str(self.board))
        return eat_piece, from_piece if not from_visible else 'x', target_piece if not target_visible else 'x'

    @staticmethod
    def get_piece_side(piece: str):
        if piece.isupper():
            return 'w'
        else:
            return 'b'

    @staticmethod
    def draw_board_to_str(board):
        board_str = ''
        count = 9
        for row in board:
            board_str += str(count) + " "
            count -= 1
            for c in row:
                if c[0] == '':
                    board_str += ' · '
                else:
                    board_str += f" {c[0]} "
            board_str += '\n'
        board_str += '   a  b  c  d  e  f  g  h  i '
        return board_str

    @staticmethod
    def get_oppo(side):
        return 'w' if side == 'b' else 'b'

    def get_dark_info(self, side):
        info = self.global_dark_pieces.copy()
        for piece, count in self.captured_pieces[side].items():
            info[piece] -= count
        return info

    def get_fen(self, side):
        board_str = self.board_to_str(self.board)
        dark_info_str = self.get_piece_count_str(self.get_dark_info(side))
        return board_str + " " + dark_info_str + " " + side


if __name__ == "__main__":
    jieqi = JieQi()
    jieqi.generate_random_board_info_from_fen("xxxxkxxxx/9/1x5x1/x1x1x1x1x/9/4F4/X1X3X1X/1X5X1/9/XXXXKXXXX r2a2c2p5n2b2R2A2C2P5N2B2 b")
    print(json.dumps(jieqi.board))
    jieqi.make_move('e3e4')
    print(jieqi.get_fen('b'))


