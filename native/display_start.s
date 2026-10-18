.syntax unified
.thumb
.globl _remed1st_start
.thumb_func _remed1st_start
_remed1st_start:
  ldr r0, [sp]
  add r1, sp, #4
  bl _remed1st_main
  bl _exit
