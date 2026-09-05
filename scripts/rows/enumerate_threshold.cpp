// Exact suffix DP followed by complete enumeration above a population threshold.
// Reuse only the independently audited local row-transition implementation.
#define main blockfree_original_main
#include "blockfree_row_dp.cpp"
#undef main
#include <functional>

int main(int argc, char** argv) {
  if (argc != 4) {
    std::cerr << "usage: enumerate_threshold n threshold output.json\n";
    return 2;
  }
  const int n = std::stoi(argv[1]), target = std::stoi(argv[2]);
  if (n < 2 || n > 10 || target <= 4) return 2;
  Solver local(n);
  const size_t states = size_t(1) << (2*n);
  constexpr int16_t UNKNOWN = -30001;
  std::vector<std::vector<int16_t>> memo(n+1, std::vector<int16_t>(states, UNKNOWN));
  uint64_t transitions = 0, memo_states = 0;
  std::function<int(int,uint32_t,uint32_t)> best = [&](int remaining, uint32_t a, uint32_t b) -> int {
    auto& result = memo[remaining][(a << n) | b];
    if (result != UNKNOWN) return result;
    ++memo_states;
    if (remaining == 0)
      return result = (local.valid_triple(a,b,0) && local.valid_triple(b,0,0)) ? 0 : NEG;
    result = NEG;
    local.enumerate_successor_rows(a,b,[&](uint32_t c) {
      ++transitions;
      int suffix = best(remaining-1,b,c);
      if (suffix != NEG) result = std::max<int>(result, std::popcount(c)+suffix);
    });
    return result;
  };
  int optimum = best(n,0,0);
  std::ofstream output(argv[3]);
  if (!output) return 2;
  output << "{\"n\":" << n << ",\"threshold\":" << target
         << ",\"blockfree_optimum\":" << optimum << ",\"row_masks\":[";
  uint64_t boards = 0;
  std::vector<uint32_t> rows;
  std::function<void(int,uint32_t,uint32_t,int)> visit = [&](int remaining,uint32_t a,uint32_t b,int population) {
    int bound = best(remaining,a,b);
    if (bound == NEG || population + bound < target) return;
    if (remaining == 0) {
      if (boards++) output << ',';
      output << '[';
      for (int i=0; i<n; ++i) { if(i) output << ','; output << rows[i]; }
      output << ']';
      return;
    }
    local.enumerate_successor_rows(a,b,[&](uint32_t c) {
      rows.push_back(c);
      visit(remaining-1,b,c,population+std::popcount(c));
      rows.pop_back();
    });
  };
  visit(n,0,0,0);
  output << "],\"board_count\":" << boards << ",\"memo_states\":" << memo_states
         << ",\"transitions\":" << transitions << "}\n";
  std::cout << "block-free optimum=" << optimum << " threshold boards=" << boards << '\n';
  return output ? 0 : 2;
}
