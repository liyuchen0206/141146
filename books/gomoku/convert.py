import regex
import argparse


def apply_transform(pos, size, transform):
    sx, sy = size - 1, size - 1
    mapping_list = [
        lambda x, y: (x, y),
        lambda x, y: (y, sy - x),
        lambda x, y: (sx - x, sy - y),
        lambda x, y: (sx - y, x),
        lambda x, y: (x, sy - y),
        lambda x, y: (sx - x, y),
        lambda x, y: (y, x),
        lambda x, y: (sx - y, sy - x),
    ]
    return [mapping_list[transform](*move) for move in pos]


def check_pos(pos, size):
    for x, y in pos:
        if x < 0 or x >= size or y < 0 or y >= size:
            return False
    return True


def pos2str(pos):
    return ''.join(chr(x + ord('a')) + str(y + 1) for x, y in pos)


def convert(srcfile, dstfile, size=15):
    with open(srcfile, 'r') as f:
        positions = [[(ord(move[0]) - ord('a'), int(move[1:]) - 1)
                      for move in regex.findall(r'[a-z][1-9][0-9]?', line.lower())]
                     for line in f.readlines() if line]

    with open(dstfile, 'w') as f:
        for t in range(8):
            for pos in positions:
                pos_t = apply_transform(pos, size, t)
                check_pos(pos_t, size)
                f.write(pos2str(pos_t) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('srcfile', type=str)
    parser.add_argument('dstfile', type=str)
    parser.add_argument('--size', type=int, default=15)
    args = parser.parse_args()
    convert(args.srcfile, args.dstfile, args.size)
