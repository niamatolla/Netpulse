#include <iostream>      // std::cout for printing
#include <cerrno>        // errno, EAGAIN
#include <cstdint>       // uint64_t
#include <sys/socket.h>  // socket, bind, recvfrom, sendto, setsockopt
#include <sys/time.h>    // timeval
#include <netinet/in.h>  // sockaddr_in, INADDR_ANY
#include <arpa/inet.h>   // htons, inet_pton
#include <unistd.h>      // close

int main(){

    // Make a UDP packet. Returns a file descriptor 
    int sock = socket(AF_INET,SOCK_DGRAM,0);

    if (sock <0 ){
        std::cerr << " socket() failed \n";
        return 1;
    }

    sockaddr_in  server_addr{};
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr= INADDR_ANY;
    server_addr.sin_port= htons(9000);

    // Bind
    if (bind(sock, (sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "bind() failed\n";
        close(sock);
        return 1;
    }


    // Wake up after 0.5 seconds without packets, so a summary of the run that
    // just ended can be printed while nothing is being timed
    timeval timeout{};
    timeout.tv_usec = 500'000;
    if (setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0) {
        std::cerr << "setsockopt() failed\n";
        close(sock);
        return 1;
    }

    std::cout << " Echo server listening in port 9000..." << std::endl;

    char buffer[1024];
    sockaddr_in  client_addr{};

    // Counters for the current run. Comparing them with the client's totals
    // shows where lost packets went missing.
    uint64_t received = 0;     // packets that reached this program
    uint64_t echoed = 0;       // replies sendto accepted
    uint64_t echo_failed = 0;  // replies sendto refused, e.g. a full send buffer

    // Looping forever and echoing whatever arrives
    while(true){
        // recvfrom overwrites client_len so reset it before every call
        socklen_t client_len = sizeof(client_addr);

        // recvfrom blocks until a packet arrives and fills client_addr with WHO sent it
        ssize_t n = recvfrom( sock, buffer, sizeof(buffer)-1, 0, (sockaddr*)&client_addr, &client_len);

        if (n < 0) {
            // Idle for 0.5 seconds: the run is over, so this is a safe moment to print
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                if (received > 0) {
                    std::cout << "run summary: received " << received
                              << ", echoed " << echoed
                              << ", failed to echo " << echo_failed << std::endl;
                    received = echoed = echo_failed = 0;
                }
                continue;
            }
            std::cerr << "recvfrom() failed\n";
            continue;
        }
        received++;

        // No printing in this loop because terminal output would be timed as network latency

        // send the exact same byte to whoever sent them
        if (sendto(sock, buffer, n,0, (sockaddr*)&client_addr,client_len ) == n) {
            echoed++;
        } else {
            echo_failed++;
        }

    }
    close(sock);
    return(0);

}