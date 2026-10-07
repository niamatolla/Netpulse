#include <iostream>      // std::cout for printing
#include <cstring>       // strlen
#include <sys/socket.h>  // socket, bind, recvfrom, sendto
#include <netinet/in.h>  // sockaddr_in, INADDR_ANY
#include <arpa/inet.h>   // htons, inet_pton
#include <unistd.h>      // closexcode-select --install

int main(){

    // Make a UDP packet. Returns a file descriptor 
    int sock = socket(AF_INET,SOCK_DGRAM,0);

    if (sock <0 ){
        std::cerr << " socket() failed \n";
        return 1;
    }

    // Describe MY OWN address. Which port the server is claiming 
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


    std::cout << " Echo server listening in port 9000...\n";

    char buffer[1024];
    sockaddr_in  client_addr{};

    // Looping forever and echoing whatever arrives
    while(true){
        // recvfrom overwrites client_len, so reset it before every call
        socklen_t client_len = sizeof(client_addr);

        // recvfrom blocks until a packet arrives and fills client_addr with WHO sent it
        ssize_t n = recvfrom( sock, buffer, sizeof(buffer)-1, 0, (sockaddr*)&client_addr, &client_len);

        if (n < 0) {
            std::cerr << "recvfrom() failed\n";
            continue;
        }

        buffer[n]= '\0';

        std::cout << "Received " <<n << "bytes\n" ;

        // send the exact same byte to whoever sent them
        sendto(sock, buffer, n,0, (sockaddr*)&client_addr,client_len );

    }
    close(sock);
    return(0);

}