#include <iostream>      // std::cout for printing
#include <cstring>       // strlen
#include <sys/socket.h>  // socket, bind, recvfrom, sendto
#include <netinet/in.h>  // sockaddr_in, INADDR_ANY
#include <arpa/inet.h>   // htons, inet_pton
#include <unistd.h>      // close

int main() {
    // Make a UDP packet

    int sock = socket(AF_INET, SOCK_DGRAM, 0);

    if( sock<0 ){
        std::cerr << "socket() failed \n";
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


    // Prepare the message
    const char* message= "hello Netpulse";
    // Sends message 
    ssize_t bytesSent = sendto(sock, message, strlen(message), 0,
                               reinterpret_cast<sockaddr*>(&server_addr), sizeof(server_addr));

    if (bytesSent < 0) {
        std::cerr << "sendto() failed\n";
        close(sock);
        return 1;
    }

    std::cout << " Sent:    "<< message<< "\n";

    //Waits for the echo to come back
    char buffer[1024];
    sockaddr_in from_addr{};
    socklen_t from_len = sizeof(from_addr);

    ssize_t bytesReceived = recvfrom(sock, buffer, sizeof(buffer) - 1, 0,
                                     reinterpret_cast<sockaddr*>(&from_addr), &from_len);

    if (bytesReceived < 0) {
        std::cerr << "recvfrom() failed\n";
        close(sock);
        return 1;
    }

    buffer[bytesReceived] = '\0';   // null-terminate so it prints cleanly as text
    std::cout << "Received: " << buffer << "\n";

    close(sock);
    return 0;

}
