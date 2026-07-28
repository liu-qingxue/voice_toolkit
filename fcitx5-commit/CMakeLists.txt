cmake_minimum_required(VERSION 3.16)
project(commitbridge)

find_package(Fcitx5Core REQUIRED)
find_package(Fcitx5Utils REQUIRED)

add_library(commitbridge MODULE commit-bridge.cpp)
target_link_libraries(commitbridge PRIVATE Fcitx5::Core Fcitx5::Utils)

install(TARGETS commitbridge DESTINATION lib/fcitx5)
install(FILES commitbridge.conf DESTINATION share/fcitx5/addon)
