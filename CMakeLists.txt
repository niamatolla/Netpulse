cmake_minimum_required(VERSION 3.16)
project(Netpulse LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Measurements need an optimised build, so Release is the default
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Put the binaries in the project root, where sweep.py and the README expect
# ./client and ./echo_server, instead of inside the build folder
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR})

find_package(Threads REQUIRED)

add_executable(echo_server src/echo_server.cpp)
add_executable(client src/client.cpp)
target_link_libraries(client PRIVATE Threads::Threads)

foreach(target echo_server client)
    target_compile_options(${target} PRIVATE -Wall -Wextra)
endforeach()
