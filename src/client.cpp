#include <iostream>      // std::cout for printing
#include <chrono>        // steady_clock for RTT timing
#include <cstdint>       // uint64_t
#include <sys/socket.h>  // socket, recvfrom, sendto, setsockopt
#include <sys/time.h>    // timeval
#include <netinet/in.h>  // sockaddr_in
#include <arpa/inet.h>   // htons, inet_pton
#include <unistd.h>      // close

// What travels in every packet. The server echoes it back untouched, so the
// reply itself says which packet it is and when it was sent.
// Only the client ever reads these fields, so no byte order conversion is needed.
struct Packet {
    uint64_t seq;           // which packet this is
    uint64_t send_time_ns;  // steady_clock reading when it was sent
};

// Current steady_clock reading in nanoseconds. Only differences are meaningful.
uint64_t now_ns() {
    auto now = std::chrono::steady_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
}

int main() {
    const int packet_count = 10;

    // Make a UDP packet

    int sock = socket(AF_INET, SOCK_DGRAM, 0);

    if( sock<0 ){
        std::cerr << "socket() failed \n";
        return 1;
    }

    // Give up on a reply after 1 second instead of blocking forever
    timeval timeout{};
    timeout.tv_sec = 1;
    if (setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0) {
        std::cerr << "setsockopt() failed\n";
        close(sock);
        return 1;
    }

    // Describes the server's address
    sockaddr_in server_addr{};
    server_addr.sin_family = AF_INET;
    if (inet_pton(AF_INET, "127.0.0.1", &server_addr.sin_addr) != 1) {
        std::cerr << "inet_pton() failed\n";
        close(sock);
        return 1;
    }
    server_addr.sin_port = htons(9000);

    // Send one packet, wait for its echo then send the next
    for (int i = 0; i < packet_count; i++) {
        // Stamp the packet as late as possible right before it leaves
        Packet out{};
        out.seq = i;
        out.send_time_ns = now_ns();

        ssize_t bytesSent = sendto(sock, &out, sizeof(out), 0,
                                   reinterpret_cast<sockaddr*>(&server_addr), sizeof(server_addr));

        if (bytesSent < 0) {
            std::cerr << "sendto() failed\n";
            close(sock);
            return 1;
        }

        // Waits for the echo to come back
        Packet in{};
        sockaddr_in from_addr{};
        socklen_t from_len = sizeof(from_addr);

        ssize_t bytesReceived = recvfrom(sock, &in, sizeof(in), 0,
                                         reinterpret_cast<sockaddr*>(&from_addr), &from_len);

        // Read the clock as early as possible right after the echo arrives
        uint64_t recv_time_ns = now_ns();

        if (bytesReceived < 0) {
            std::cout << "seq=" << out.seq << " timed out\n";
            continue;
        }

        if (bytesReceived != sizeof(in) || in.seq != out.seq) {
            std::cout << "seq=" << out.seq << " unexpected reply\n";
            continue;
        }

        // RTT comes from the timestamp carried inside the echoed packet
        uint64_t rtt_us = (recv_time_ns - in.send_time_ns) / 1000;
        std::cout << "seq=" << in.seq << " rtt=" << rtt_us << " us\n";
    }

    close(sock);
    return 0;

}
