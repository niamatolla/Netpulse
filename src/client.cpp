#include <iostream>      // std::cout for printing
#include <algorithm>     // std::sort, std::min
#include <atomic>        // std::atomic, shared between the two threads
#include <chrono>        // steady_clock for RTT timing
#include <cmath>         // std::ceil
#include <cstdint>       // uint64_t
#include <cstdio>        // printf
#include <cstdlib>       // strtol
#include <cstring>       // strcmp
#include <thread>        // std::thread, sleep_for
#include <vector>        // std::vector, one RTT slot per packet
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

// Marks an RTT slot whose reply has not arrived
const uint64_t NOT_RECEIVED = UINT64_MAX;

// How long to keep listening for late replies after the last packet is sent
const uint64_t GRACE_NS = 1'000'000'000;

// Sleeping is imprecise, so the sender sleeps until this close to a send time
// and then spins on the clock for the rest
const uint64_t SPIN_NS = 1'000'000;

// Current steady_clock reading in nanoseconds. Only differences are meaningful.
uint64_t now_ns() {
    auto now = std::chrono::steady_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
}

// Nearest-rank percentile of an already sorted list: the smallest value that
// at least p percent of the samples are less than or equal to
uint64_t percentile(const std::vector<uint64_t>& sorted, double p) {
    size_t rank = static_cast<size_t>(std::ceil(p / 100.0 * sorted.size()));
    if (rank < 1) rank = 1;
    return sorted[rank - 1];
}

int main(int argc, char* argv[]) {
    // Usage: ./client [rate in packets per second] [duration in seconds] [--csv]
    // --csv prints the result as one comma-separated line, for sweep.py to read
    long rate = 1000;
    long duration = 5;
    bool csv = false;
    if (argc > 1 && std::strcmp(argv[argc - 1], "--csv") == 0) {
        csv = true;
        argc--;
    }
    if (argc > 1) rate = std::strtol(argv[1], nullptr, 10);
    if (argc > 2) duration = std::strtol(argv[2], nullptr, 10);

    if (argc > 3 || rate < 1 || rate > 1'000'000 || duration < 1 || duration > 3600) {
        std::cerr << "usage: " << argv[0] << " [rate_pps] [duration_seconds] [--csv]\n";
        return 1;
    }

    // The first packets of a run are slower than the rest while caches and the
    // scheduler warm up. So extra warm-up packets are sent first, at the same
    // rate, and left out of the results: at most 100 of them or 1 second's worth.
    const uint64_t warmup = std::min<uint64_t>(100, rate);
    const uint64_t measured = static_cast<uint64_t>(rate) * duration;
    const uint64_t total = warmup + measured;
    const uint64_t interval_ns = 1'000'000'000 / rate;

    // Make a UDP packet

    int sock = socket(AF_INET, SOCK_DGRAM, 0);

    if( sock<0 ){
        std::cerr << "socket() failed \n";
        return 1;
    }

    // Wake the receiver every 100 ms even when nothing arrives, so it can
    // notice that the run is over instead of blocking forever
    timeval timeout{};
    timeout.tv_usec = 100'000;
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

    // One RTT slot per packet allocated up front so nothing allocates
    // while the run is being timed. The slot index is the packet's seq.
    std::vector<uint64_t> rtt_ns(total, NOT_RECEIVED);

    // Set by the sender once its last packet has left. 0 means still sending.
    std::atomic<uint64_t> send_end_ns{0};

    // Receiver thread: timestamps every echo the moment it arrives.
    // It is the only thread that writes rtt_ns until it has been joined.
    // received counts every echo, warm-up included, so it can stop early
    uint64_t received = 0;
    std::thread receiver([&]() {
        while (received < total) {
            Packet in{};
            ssize_t bytesReceived = recvfrom(sock, &in, sizeof(in), 0, nullptr, nullptr);

            // Read the clock as early as possible right after the echo arrives
            uint64_t recv_time_ns = now_ns();

            // Once sending is over, stragglers get a grace period and then we stop
            uint64_t end = send_end_ns.load();
            if (end != 0 && recv_time_ns > end + GRACE_NS) break;

            if (bytesReceived != sizeof(in)) continue;      // timeout or junk
            if (in.seq >= total) continue;                  // not one of ours
            if (rtt_ns[in.seq] != NOT_RECEIVED) continue;   // duplicate

            // RTT comes from the timestamp carried inside the echoed packet
            rtt_ns[in.seq] = recv_time_ns - in.send_time_ns;
            received++;
        }
    });

    // Open loop. Packet i leaves at start + i * interval, whether or
    // not any reply has come back.
    // sent and the two send times only cover the measured packets, not warm-up
    uint64_t sent = 0;
    uint64_t first_send_ns = 0;
    uint64_t last_send_ns = 0;
    const uint64_t start_ns = now_ns();

    for (uint64_t i = 0; i < total; i++) {
        // Absolute schedule so a late send does not push every later one back
        uint64_t target_ns = start_ns + i * interval_ns;

        uint64_t now = now_ns();
        if (target_ns > now + SPIN_NS) {
            std::this_thread::sleep_for(std::chrono::nanoseconds(target_ns - now - SPIN_NS));
        }
        while (now_ns() < target_ns) {
            // spin until the exact send time
        }

        // Stamp the packet as late as possible right before it leaves
        Packet out{};
        out.seq = i;
        out.send_time_ns = now_ns();

        ssize_t bytesSent = sendto(sock, &out, sizeof(out), 0,
                                   reinterpret_cast<sockaddr*>(&server_addr), sizeof(server_addr));

        // A failed sendis skipped, not retried:
        // retrying would break the fixed schedule
        if (bytesSent == sizeof(out) && i >= warmup) {
            if (sent == 0) first_send_ns = out.send_time_ns;
            sent++;
            last_send_ns = out.send_time_ns;
        }
    }

    send_end_ns.store(now_ns());
    receiver.join();
    close(sock);

    // Rate actually achieved: sent packets span (sent - 1) intervals
    double achieved = 0;
    if (sent > 1) {
        achieved = (sent - 1) * 1e9 / (last_send_ns - first_send_ns);
    }

    // Collect the RTTs of the measured packets, skipping the warm-up ones
    std::vector<uint64_t> samples;
    samples.reserve(measured);
    for (uint64_t seq = warmup; seq < total; seq++) {
        if (rtt_ns[seq] != NOT_RECEIVED) samples.push_back(rtt_ns[seq]);
    }
    std::sort(samples.begin(), samples.end());

    uint64_t measured_received = samples.size();
    uint64_t lost = sent - measured_received;
    double loss_pct = sent > 0 ? 100.0 * lost / sent : 0.0;

    if (csv) {
        // target_pps,achieved_pps,sent,received,lost,loss_pct,p50_us,p95_us,p99_us
        // The three percentiles are left empty when no reply came back
        std::printf("%ld,%.0f,%llu,%llu,%llu,%.4f,", rate, achieved,
                    static_cast<unsigned long long>(sent),
                    static_cast<unsigned long long>(measured_received),
                    static_cast<unsigned long long>(lost), loss_pct);
        if (samples.empty()) {
            std::printf(",,\n");
            return 1;
        }
        std::printf("%.1f,%.1f,%.1f\n",
                    percentile(samples, 50) / 1000.0,
                    percentile(samples, 95) / 1000.0,
                    percentile(samples, 99) / 1000.0);
        return 0;
    }

    std::printf("target rate: %ld pps   achieved: %.0f pps\n", rate, achieved);
    std::printf("sent: %llu   received: %llu   lost: %llu (%.2f%%)\n",
                static_cast<unsigned long long>(sent),
                static_cast<unsigned long long>(measured_received),
                static_cast<unsigned long long>(lost), loss_pct);

    if (samples.empty()) {
        std::printf("no replies to measure\n");
        return 1;
    }

    std::printf("p50: %.1f us   p95: %.1f us   p99: %.1f us   (%zu samples, after %llu warm-up packets)\n",
                percentile(samples, 50) / 1000.0,
                percentile(samples, 95) / 1000.0,
                percentile(samples, 99) / 1000.0,
                samples.size(),
                static_cast<unsigned long long>(warmup));

    return 0;

}
