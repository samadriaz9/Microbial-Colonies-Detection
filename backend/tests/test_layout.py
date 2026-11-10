from app.services.layout import natural_key, slots

STAGE_7X4 = [
    [1, 14, 15, 28],
    [2, 13, 16, 27],
    [3, 12, 17, 26],
    [4, 11, 18, 25],
    [5, 10, 19, 24],
    [6, 9, 20, 23],
    [7, 8, 21, 22],
]


def test_scanner_matches_stage_path():
    placed = [[None] * 4 for _ in range(7)]
    for index, (row, col) in enumerate(slots(7, 4, "scanner"), start=1):
        placed[row][col] = index
    assert placed == STAGE_7X4


def test_row_layout_is_row_major():
    assert slots(2, 3, "row") == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]


def test_natural_filename_order():
    names = ["10.jpg", "2.jpg", "1.jpg", "img_03.png"]
    assert sorted(names, key=natural_key) == ["1.jpg", "2.jpg", "10.jpg", "img_03.png"]
