# Determinism over speed where they conflict.
#
# -march=native is DELIBERATELY ABSENT. It compiles for the build machine's
# instruction set, so two nodes with different CPUs could produce different
# pixels and seam at tile boundaries. -ffp-contract=off stops the compiler
# fusing a*b+c into an FMA, which changes intermediate rounding for the same
# reason. Both are load-bearing for distributed rendering, not style choices.
CXX      ?= g++
CXXFLAGS := -O3 -fPIC -std=c++17 -ffp-contract=off -fno-fast-math -Wall -Wextra

libforge_core.so: forge_core.cpp
	$(CXX) $(CXXFLAGS) -shared -o $@ $<

clean:
	rm -f libforge_core.so
