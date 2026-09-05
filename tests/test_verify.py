from pathlib import Path
import sys


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from csl_verify import bounding_square, pad_grid, verify_grid  # noqa: E402


def test_block_is_stable_connected_and_translation_invariant():
    block = [[1, 1], [1, 1]]
    assert verify_grid(block, claimed_cells=4).valid
    padded = pad_grid(block, 5, row_offset=2, col_offset=1)
    result = verify_grid(padded, claimed_cells=4)
    assert result.valid
    assert result.population == 4


def test_exterior_birth_is_detected():
    # Three live boundary cells give birth immediately above the grid.
    result = verify_grid(
        [
            [1, 1, 1],
            [0, 0, 0],
            [0, 0, 0],
        ]
    )
    assert not result.valid
    assert any(
        item["type"] == "birth" and item["cell"][0] == -1
        for item in result.violations
    )


def test_disconnected_blocks_are_rejected():
    result = verify_grid(
        [
            [1, 1, 0, 0, 0],
            [1, 1, 0, 0, 0],
            [0, 0, 0, 0, 0],
            [0, 0, 0, 1, 1],
            [0, 0, 0, 1, 1],
        ]
    )
    assert result.stable
    assert not result.connected
    assert not result.valid


def test_bounding_square_crops_empty_margin():
    grid = [
        [0, 0, 0, 0, 0],
        [0, 1, 1, 0, 0],
        [0, 1, 1, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
    ]
    cropped, bounds = bounding_square(grid)
    assert cropped == [[1, 1], [1, 1]]
    assert bounds == (1, 2, 1, 2)

