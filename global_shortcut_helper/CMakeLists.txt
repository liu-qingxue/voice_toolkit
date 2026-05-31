cmake_minimum_required(VERSION 3.16)
project(global-shortcut-helper LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui)
find_package(KF6GlobalAccel REQUIRED)

add_executable(global-shortcut-helper main.cpp)
target_link_libraries(global-shortcut-helper
    PRIVATE
    Qt6::Core
    Qt6::Gui
    KF6::GlobalAccel
)
