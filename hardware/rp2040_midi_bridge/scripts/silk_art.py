"""Silkscreen artwork shared by the board generator and the silk updater.

The board name and the USB-A pin labels go on the back side so the connector
body cannot hide them.  The back side also carries a QR code for the repository
URL.  The QR code is drawn as a white silkscreen field with the dark modules
left as bare solder mask, so a normal (dark-on-light) scanner can read it from
the bottom of the board.  The BOOT and RUN tact switches get their function
labels on the front silk, next to the switch reference designators.
"""

from __future__ import annotations

import pcbnew

MM = pcbnew.FromMM

BOARD_NAME = "RP2040 MIDI BRIDGE"
BOARD_NAME_POS = (29.0, 9.5)
BOARD_NAME_SIZE = 0.8

J2_LABEL = "J2 USB-A (TOP)"
J2_LABEL_POS = (29.0, 33.0)
J2_LABEL_SIZE = 0.8

J2_PIN_LABELS = (
    ("VCC", 32.5),
    ("D-", 30.0),
    ("D+", 28.0),
    ("GND", 25.5),
)
J2_PIN_LABEL_Y = 38.0
J2_PIN_LABEL_SIZE = 0.8
J2_PIN_LABEL_THICKNESS = 0.12

# Function labels for the BOOT (SW6) and RUN (SW7) tact switches.  They sit to
# the right of the switches, clear of SW4 and the J2 connector body.
SW_LABELS = (("BOOT", 8.6, 33.2), ("RUN", 8.6, 37.4))
SW_LABEL_SIZE = 0.8
SW_LABEL_THICKNESS = 0.12

# Labels from earlier revisions that remove_art() must also clean up.
LEGACY_LABELS = {"VBUS", "VCC", "D-", "D+", "GND", J2_LABEL}
SW_LABEL_TEXTS = {label for label, _, _ in SW_LABELS}

QR_REPO_URL = "https://github.com/nananek/genshin-midi-board"
QR_CENTER = (29.0, 17.5)
QR_MODULE_MM = 0.30
QR_QUIET_MODULES = 4

# qrencode -t ASCII -l M -m 0 'https://github.com/nananek/genshin-midi-board'
# 33 x 33 modules, version 4, ECC M.  '1' is a dark module.
QR_MATRIX = (
    "111111100111000010111101001111111",
    "100000100111100110101110001000001",
    "101110101111101110000100001011101",
    "101110101111100100100100101011101",
    "101110101110011111001101001011101",
    "100000101110111001010000101000001",
    "111111101010101010101010101111111",
    "000000001100100010111101100000000",
    "101111100001111001010000001111100",
    "000000010100111011111001001101101",
    "111101110011011111000010101010110",
    "101001001100010011111000110011110",
    "101011110110101110011111000111001",
    "010110000111110100100001001001011",
    "010001111100111110101010011100010",
    "110010011011100100000100111000100",
    "100111101111000101000010110110001",
    "010100011010110010111101001101101",
    "111111101011110110101100111110110",
    "110100010100000010011110010111100",
    "100100110010101000110100110111001",
    "100100001000100111001111001001001",
    "101001101011110001010000010001110",
    "101111010111111010111111011111110",
    "101111111010000001010011111110011",
    "000000001000111001110001100010101",
    "111111100001011111001011101010110",
    "100000101101001001101001100011111",
    "101110101100111010011110111111000",
    "101110101010000100100001110011001",
    "101110101010001110001010001101100",
    "100000100001100100000110000011100",
    "111111101110111101000011101100010",
)
assert len(QR_MATRIX) == 33 and all(len(row) == 33 for row in QR_MATRIX)

QR_SIDE_MM = (len(QR_MATRIX) + 2 * QR_QUIET_MODULES) * QR_MODULE_MM
QR_LEFT = QR_CENTER[0] - QR_SIDE_MM / 2
QR_TOP = QR_CENTER[1] - QR_SIDE_MM / 2
QR_RIGHT = QR_LEFT + QR_SIDE_MM
QR_BOTTOM = QR_TOP + QR_SIDE_MM


def _add_text(
    board: pcbnew.BOARD,
    text: str,
    x_mm: float,
    y_mm: float,
    size_mm: float,
    thickness_mm: float,
    layer: int,
    mirrored: bool,
) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetLayer(layer)
    item.SetPosition(pcbnew.VECTOR2I(MM(x_mm), MM(y_mm)))
    item.SetTextSize(pcbnew.VECTOR2I(MM(size_mm), MM(size_mm)))
    item.SetTextThickness(MM(thickness_mm))
    item.SetMirrored(mirrored)
    item.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    item.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    board.Add(item)


def _add_rect(
    board: pcbnew.BOARD,
    x0_mm: float,
    y0_mm: float,
    x1_mm: float,
    y1_mm: float,
    layer: int,
) -> None:
    item = pcbnew.PCB_SHAPE(board)
    item.SetShape(pcbnew.SHAPE_T_RECT)
    item.SetStart(pcbnew.VECTOR2I(MM(x0_mm), MM(y0_mm)))
    item.SetEnd(pcbnew.VECTOR2I(MM(x1_mm), MM(y1_mm)))
    item.SetLayer(layer)
    item.SetFilled(True)
    item.SetWidth(0)
    board.Add(item)


def remove_art(board: pcbnew.BOARD) -> None:
    """Remove earlier versions of the back-side art and the old board name."""
    for item in list(board.GetDrawings()):
        if isinstance(item, pcbnew.PCB_TEXT):
            if "RP2040 MIDI BRIDGE" in item.GetText():
                board.Remove(item)
            elif item.GetLayer() == pcbnew.B_SilkS and item.GetText() in LEGACY_LABELS:
                board.Remove(item)
            elif item.GetLayer() == pcbnew.F_SilkS and item.GetText() in SW_LABEL_TEXTS:
                board.Remove(item)
        elif isinstance(item, pcbnew.PCB_SHAPE):
            if item.GetLayer() != pcbnew.B_SilkS:
                continue
            box = item.GetBoundingBox()
            left, top = pcbnew.ToMM(box.GetLeft()), pcbnew.ToMM(box.GetTop())
            right, bottom = pcbnew.ToMM(box.GetRight()), pcbnew.ToMM(box.GetBottom())
            if (left >= QR_LEFT - 0.1 and right <= QR_RIGHT + 0.1
                    and top >= QR_TOP - 0.1 and bottom <= QR_BOTTOM + 0.1):
                board.Remove(item)


def add_art(board: pcbnew.BOARD) -> None:
    """Draw the board name, USB-A labels and QR code on the back side."""
    remove_art(board)

    _add_text(board, BOARD_NAME, *BOARD_NAME_POS, BOARD_NAME_SIZE, 0.12,
              pcbnew.B_SilkS, mirrored=True)
    _add_text(board, J2_LABEL, *J2_LABEL_POS, J2_LABEL_SIZE, 0.10,
              pcbnew.B_SilkS, mirrored=True)
    for label, x_mm in J2_PIN_LABELS:
        _add_text(board, label, x_mm, J2_PIN_LABEL_Y, J2_PIN_LABEL_SIZE,
                  J2_PIN_LABEL_THICKNESS, pcbnew.B_SilkS, mirrored=True)
    for label, x_mm, y_mm in SW_LABELS:
        _add_text(board, label, x_mm, y_mm, SW_LABEL_SIZE,
                  SW_LABEL_THICKNESS, pcbnew.F_SilkS, mirrored=False)

    # Draw white (silk) cells for the light modules and the quiet zone.  The
    # dark modules stay as bare green solder mask.  Columns are mirrored so the
    # code reads correctly when the board is viewed from the bottom.
    n = len(QR_MATRIX)
    ext = n + 2 * QR_QUIET_MODULES

    def is_light(row: int, col: int) -> bool:
        if QR_QUIET_MODULES <= row < QR_QUIET_MODULES + n and \
                QR_QUIET_MODULES <= col < QR_QUIET_MODULES + n:
            return QR_MATRIX[row - QR_QUIET_MODULES][col - QR_QUIET_MODULES] == "0"
        return True

    # Merge consecutive light modules into one rectangle per run so the board
    # file does not need one shape for every module.
    for row in range(ext):
        col = 0
        y0 = QR_TOP + row * QR_MODULE_MM
        while col < ext:
            if not is_light(row, col):
                col += 1
                continue
            start = col
            while col < ext and is_light(row, col):
                col += 1
            x_left = QR_LEFT + (ext - col) * QR_MODULE_MM
            x_right = QR_LEFT + (ext - start) * QR_MODULE_MM
            _add_rect(board, x_left, y0, x_right, y0 + QR_MODULE_MM,
                      pcbnew.B_SilkS)
