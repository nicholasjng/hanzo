"""Ninja rule definitions in Python."""

# TODO: Instead of string templates, use actual Python rule classes later.
cc_compile = """
rule cc
  depfile = $depfile
  deps = gcc
  command = {compiler} $defines $includes $flags -MD -MT $out -MF $depfile -o $out -c $in
  description = Building C++ object $out
"""

cc_linkstatic = """
rule cc-linkstatic
  command = $pre_link && rm -f $target_file && {archiver} $target_file $linkflags $in && {ranlib} $target_file && touch $target_file && $post_build
  description = Linking C++ static library $target_file
  restat = $restat
"""

cc_linkshared = """
rule cc_linkshared
  command = $pre_link && {compiler} $cflags $archflags $ldflags -o $target_file $in $link_path $link_libraries && $post_build
  description = Linking C++ shared module $target_file
  restat = $restat
"""
