"""Proven ordinary still-life maxima through n=60.

These are Chu--Stuckey (2012), Table 7.  Every connected still life is an
ordinary still life, so each value is also a valid connected upper bound.
The values at n=24 and n=26 are 302 and 353, respectively.
"""

ORDINARY_MAXIMUM = {
    1: 0,
    2: 4,
    3: 6,
    4: 8,
    5: 16,
    6: 18,
    7: 28,
    8: 36,
    9: 43,
    10: 54,
    11: 64,
    12: 76,
    13: 90,
    14: 104,
    15: 119,
    16: 136,
    17: 152,
    18: 171,
    19: 190,
    20: 210,
    21: 232,
    22: 253,
    23: 276,
    24: 302,
    25: 326,
    26: 353,
    27: 379,
    28: 407,
    29: 437,
    30: 467,
    31: 497,
    32: 531,
    33: 563,
    34: 598,
    35: 633,
    36: 668,
    37: 706,
    38: 744,
    39: 782,
    40: 824,
    41: 864,
    42: 907,
    43: 949,
    44: 993,
    45: 1039,
    46: 1085,
    47: 1132,
    48: 1181,
    49: 1229,
    50: 1280,
    51: 1331,
    52: 1382,
    53: 1436,
    54: 1490,
    55: 1545,
    56: 1602,
    57: 1658,
    58: 1717,
    59: 1776,
    60: 1835,
}


# The depth-three exhaustive 4x4-corner transducer joined to the certified
# block-free width-three edge automaton.  Every connected still life with more
# than four cells is block-free, so this is a rigorous connected upper bound.
#
# The finite certificate checks n=10,...,64.  Its full min-plus edge matrix
# satisfies A[L+8]=A[L]+3 from L=20 onward, which inductively proves the same
# formula for every larger n.
BLOCKFREE_CORNER_RING_CHARGE = (18, 15, 10, 15, 12, 15, 18, 3)


def blockfree_corner_ring_upper(n: int) -> int:
    """Rigorous connected-population upper bound for every n>=10."""

    if n < 10:
        raise ValueError("corner-ring theorem is stated for n>=10")
    charge = BLOCKFREE_CORNER_RING_CHARGE[n % 8]
    return (4 * n * n + 5 * n - charge) // 8


# The depth-four relaxation charges a depth-four boundary belt and enumerates exact 5x5
# corners.  A complete 711-by-809 restricted path-matrix equality proves the
# period-eight recurrence from n=32 onward; finite exact composition covers
# n=14 through the induction bases.
DEPTH4_CORNER_RING_CHARGE = (18, 23, 18, 23, 20, 15, 26, 11)


def depth4_corner_ring_upper(n: int) -> int:
    """Rigorous connected-population upper bound for every n>=14."""

    if n < 14:
        raise ValueError("depth-four ring theorem is stated for n>=14")
    charge = DEPTH4_CORNER_RING_CHARGE[n % 8]
    return (4 * n * n + 5 * n - charge) // 8


# The depth-five relaxation charges a fifth boundary layer.  Exact bases at
# n=21,29,37,45 and the complete restricted path-matrix equality from
# n=45 to n=53 prove one further cell in residue five forever.
def depth5_residue5_upper(n: int) -> int:
    """Rigorous upper for n>=21 with n mod 8=5."""

    if n < 21 or n % 8 != 5:
        raise ValueError(
            "depth-five residue theorem needs n>=21 and n mod 8=5"
        )
    return depth4_corner_ring_upper(n) - 1


# Phases 030, 031, and 033 together prove the user-supplied candidate
# U3(n)-1 in all eight residues.  The vector is the depth-three vector plus
# eight because subtracting one commutes with the floor.
ALL_RESIDUE_CONNECTED_CHARGE = (26, 23, 18, 23, 20, 23, 26, 11)


def all_residue_connected_upper(n: int) -> int:
    """Rigorous connected-population upper bound for every n>=14."""

    if n < 14:
        raise ValueError("all-residue upper theorem is stated for n>=14")
    charge = ALL_RESIDUE_CONNECTED_CHARGE[n % 8]
    return (4 * n * n + 5 * n - charge) // 8
