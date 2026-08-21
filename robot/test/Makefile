# Host tests for the weapon controller.
#
# These compile the real robot/main/src/weapon_controller.c against small
# stubs and run it natively, so the logic under test is the shipped logic.
# No ESP-IDF, no hardware, no flash cycle: `make` and read the output.
#
#   make        build and run both suites
#   make clean

MAIN    := ../main
CFLAGS  := -std=c11 -Wall -Wextra -O1 -I. -I$(MAIN)/include -include stubs.h
LDLIBS  := -lm

# Candidate gains used only to exercise the saturated path. The shipped gains
# are zero, which would make every windup assertion vacuous.
TEST_GAINS := -DWEAPON_KP=0.004f -DWEAPON_KI=0.02f

.PHONY: all clean
all: run

test_weapon: test_weapon.c $(MAIN)/src/weapon_controller.c stubs.h esp_timer.h
	$(CC) $(CFLAGS) $< $(MAIN)/src/weapon_controller.c $(LDLIBS) -o $@

test_windup: test_windup.c $(MAIN)/src/weapon_controller.c stubs.h esp_timer.h
	$(CC) $(CFLAGS) $(TEST_GAINS) $< $(MAIN)/src/weapon_controller.c $(LDLIBS) -o $@

run: test_weapon test_windup
	@./test_weapon
	@./test_windup

clean:
	@rm -f test_weapon test_windup
