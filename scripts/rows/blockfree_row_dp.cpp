#include <algorithm>
#include <bit>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

// Exact row-transfer dynamic program for block-free B3/S23 still lifes in
// an n by n box with a dead exterior.  The finite state is the ordered pair
// (a,b) of the two most recent row masks.  A transition (a,b)->(b,c) is
// admitted exactly when the middle row b and its two side-exterior cells are
// stable and no live 2x2 block is formed between b and c.

namespace {
constexpr int16_t NEG = int16_t(-30000);

uint64_t splitmix64(uint64_t z) {
  z += 0x9e3779b97f4a7c15ULL;
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}

std::string hex64(uint64_t x) {
  std::ostringstream out;
  out << std::hex << std::setfill('0') << std::setw(16) << x;
  return out.str();
}

struct LayerRecord {
  int index = 0;
  uint64_t states = 0;
  int maximum = -1;
  uint64_t transitions_cumulative = 0;
  uint64_t digest_sum = 0;
  uint64_t digest_xor = 0;
  uint64_t digest_weighted = 0;
};

struct Solver {
  int n;
  uint32_t row_mask;
  std::vector<int16_t> cur, nxt;
  std::vector<uint32_t> active, next_active;
  uint64_t transitions = 0;
  std::vector<LayerRecord> records;
  LayerRecord bottom_record;

  explicit Solver(int width) : n(width), row_mask((uint32_t(1) << n) - 1) {
    if (n < 1 || n > 14) {
      std::cerr << "dense implementation supports 1 <= n <= 14\n";
      std::exit(2);
    }
    const size_t states = size_t(1) << (2 * n);
    cur.assign(states, NEG);
    nxt.assign(states, NEG);
  }

  inline bool cell_stable(uint32_t a, uint32_t b, uint32_t c, int j) const {
    const int lo = std::max(0, j - 1);
    const int hi = std::min(n - 1, j + 1);
    const uint32_t window = ((uint32_t(1) << (hi - lo + 1)) - 1) << lo;
    int neighbours = std::popcount(a & window) + std::popcount(c & window);
    if (j > 0) neighbours += int((b >> (j - 1)) & 1u);
    if (j + 1 < n) neighbours += int((b >> (j + 1)) & 1u);
    const bool alive = ((b >> j) & 1u) != 0;
    return alive ? (neighbours == 2 || neighbours == 3) : (neighbours != 3);
  }

  inline bool valid_triple(uint32_t a, uint32_t b, uint32_t c) const {
    // Dead exterior cells immediately to the left and right of row b.
    if ((a & 1u) && (b & 1u) && (c & 1u)) return false;
    const uint32_t right = uint32_t(1) << (n - 1);
    if ((a & right) && (b & right) && (c & right)) return false;

    // No live 2x2 block straddling rows b and c.
    if (((b & (b >> 1)) & (c & (c >> 1))) != 0) return false;

    for (int j = 0; j < n; ++j) {
      if (!cell_stable(a, b, c, j)) return false;
    }
    return true;
  }

  template <class Emit>
  void enumerate_successor_rows(uint32_t a, uint32_t b, Emit&& emit) const {
    // Build c from left to right.  Once bit c_j has been selected, stability
    // of b_{j-1} is fully determined.  This visits every c exactly once.
    struct Frame { int next_column; uint32_t partial_c; };
    std::vector<Frame> stack;
    stack.reserve(2 * n + 4);
    stack.push_back({0, 0});

    while (!stack.empty()) {
      const Frame f = stack.back();
      stack.pop_back();
      const int j = f.next_column;
      const uint32_t partial = f.partial_c;

      if (j == n) {
        if (!cell_stable(a, b, partial, n - 1)) continue;
        const uint32_t right = uint32_t(1) << (n - 1);
        if ((a & right) && (b & right) && (partial & right)) continue;
        emit(partial);
        continue;
      }

      // Reverse push order makes the traversal deterministic (zero first).
      for (int value = 1; value >= 0; --value) {
        const uint32_t c = partial | (uint32_t(value) << j);
        if (j == 0 && value && (a & 1u) && (b & 1u)) continue;
        if (j >= 1) {
          if (value && ((c >> (j - 1)) & 1u) && ((b >> (j - 1)) & 3u) == 3u)
            continue;
          if (!cell_stable(a, b, c, j - 1)) continue;
        }
        stack.push_back({j + 1, c});
      }
    }
  }

  void clear_next() {
    for (uint32_t key : next_active) nxt[key] = NEG;
    next_active.clear();
  }

  void update(uint32_t key, int value) {
    if (nxt[key] == NEG) next_active.push_back(key);
    if (value > nxt[key]) nxt[key] = int16_t(value);
  }

  LayerRecord record_layer(int index, int maximum) const {
    LayerRecord r;
    r.index = index;
    r.states = active.size();
    r.maximum = maximum;
    r.transitions_cumulative = transitions;
    for (uint32_t key : active) {
      const uint64_t payload = (uint64_t(key) << 16) ^ uint16_t(cur[key]);
      const uint64_t h1 = splitmix64(payload ^ 0x243f6a8885a308d3ULL);
      const uint64_t h2 = splitmix64(payload ^ 0x13198a2e03707344ULL);
      r.digest_sum += h1;
      r.digest_xor ^= h2;
      r.digest_weighted += h1 * (uint64_t(key) + 0x9e3779b97f4a7c15ULL);
    }
    return r;
  }

  int solve() {
    cur[0] = 0;
    active.push_back(0);

    for (int row = 0; row < n; ++row) {
      clear_next();
      int layer_max = -1;
      for (uint32_t key : active) {
        const uint32_t a = key >> n;
        const uint32_t b = key & row_mask;
        const int base = cur[key];
        enumerate_successor_rows(a, b, [&](uint32_t c) {
          ++transitions;
          const int value = base + std::popcount(c);
          update((b << n) | c, value);
          layer_max = std::max(layer_max, value);
        });
      }
      for (uint32_t key : active) cur[key] = NEG;
      active.swap(next_active);
      cur.swap(nxt);
      records.push_back(record_layer(row + 1, layer_max));
      const auto& r = records.back();
      std::cerr << "layer " << r.index << " states " << r.states
                << " max " << r.maximum << " transitions "
                << r.transitions_cumulative << " digest "
                << hex64(r.digest_sum) << ":" << hex64(r.digest_xor)
                << ":" << hex64(r.digest_weighted) << "\n";
      if (active.empty()) return -1;
    }

    // The first forced zero row validates the final in-box row.
    clear_next();
    for (uint32_t key : active) {
      const uint32_t a = key >> n;
      const uint32_t b = key & row_mask;
      if (valid_triple(a, b, 0)) {
        ++transitions;
        update(b << n, cur[key]);
      }
    }
    for (uint32_t key : active) cur[key] = NEG;
    active.swap(next_active);
    cur.swap(nxt);
    int bottom_max = -1;
    for (uint32_t key : active) bottom_max = std::max(bottom_max, int(cur[key]));
    bottom_record = record_layer(n + 1, bottom_max);
    std::cerr << "bottom-1 states " << bottom_record.states
              << " max " << bottom_record.maximum << " transitions "
              << bottom_record.transitions_cumulative << " digest "
              << hex64(bottom_record.digest_sum) << ":"
              << hex64(bottom_record.digest_xor) << ":"
              << hex64(bottom_record.digest_weighted) << "\n";

    // The second forced zero row validates the bottom exterior row.
    int answer = -1;
    for (uint32_t key : active) {
      const uint32_t a = key >> n;
      const uint32_t b = key & row_mask;
      if (valid_triple(a, b, 0)) answer = std::max(answer, int(cur[key]));
    }
    return answer;
  }

  std::string json(int optimum, double seconds, const std::string& compiler) const {
    std::ostringstream out;
    out << "{\n"
        << "  \"schema\": \"blockfree-row-dp-certificate-v2\",\n"
        << "  \"n\": " << n << ",\n"
        << "  \"optimum\": " << optimum << ",\n"
        << "  \"transitions_examined\": " << transitions << ",\n"
        << "  \"seconds\": " << std::setprecision(12) << seconds << ",\n"
        << "  \"compiler\": \"" << compiler << "\",\n"
        << "  \"layers\": [\n";
    for (size_t i = 0; i < records.size(); ++i) {
      const auto& r = records[i];
      out << "    {\"index\": " << r.index
          << ", \"states\": " << r.states
          << ", \"maximum\": " << r.maximum
          << ", \"transitions_cumulative\": " << r.transitions_cumulative
          << ", \"digest_sum\": \"" << hex64(r.digest_sum)
          << "\", \"digest_xor\": \"" << hex64(r.digest_xor)
          << "\", \"digest_weighted\": \"" << hex64(r.digest_weighted)
          << "\"}" << (i + 1 == records.size() ? "\n" : ",\n");
    }
    out << "  ],\n"
        << "  \"bottom_1\": {\"states\": " << bottom_record.states
        << ", \"maximum\": " << bottom_record.maximum
        << ", \"transitions_cumulative\": " << bottom_record.transitions_cumulative
        << ", \"digest_sum\": \"" << hex64(bottom_record.digest_sum)
        << "\", \"digest_xor\": \"" << hex64(bottom_record.digest_xor)
        << "\", \"digest_weighted\": \"" << hex64(bottom_record.digest_weighted)
        << "\"}\n} \n";
    return out.str();
  }
};
}  // namespace

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "usage: blockfree_row_dp_certified n [json-output] [compiler-label]\n";
    return 2;
  }
  const int n = std::stoi(argv[1]);
  const std::string compiler = argc >= 4 ? argv[3] : "unspecified";
  const auto start = std::chrono::steady_clock::now();
  Solver solver(n);
  const int optimum = solver.solve();
  const double seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - start).count();
  const std::string result = solver.json(optimum, seconds, compiler);
  std::cout << result;
  if (argc >= 3) {
    std::ofstream file(argv[2]);
    if (!file) {
      std::cerr << "cannot open output file\n";
      return 3;
    }
    file << result;
  }
  return 0;
}
