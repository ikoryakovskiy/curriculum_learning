#!/bin/bash

echo -en "\033[1;32m --- Download results --- \033[0m\n"
ssh ikoryakovskiy@calcutron "cd drl/cl && tar --use-compress-program=pbzip2 --exclude CMake*.txt -cf results.tar.bz2 *.meta *.index *.data-* *.yaml *.csv *.pkl"
scp ikoryakovskiy@calcutron:~/drl/cl/results.tar.bz2 ./
tar --use-compress-program=pbzip2 -xvf results.tar.bz2 -C ./
rm ./results.tar.bz2

