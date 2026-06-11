#include "app/App.hpp"
#include "util/Log.hpp"

#include <chrono>
#include <exception>
#include <string>
#include <thread>

int main(int argc, char **argv) {
    while(true) {
        try {
            femto::App app;
            return app.run(argc, argv);
        }
        catch(const std::exception &ex) {
            femto::log::stderrError(std::string("Fatal service error; restarting in 5 seconds: ") + ex.what());
        }
        catch(...) {
            femto::log::stderrError("Fatal unknown service error; restarting in 5 seconds");
        }
        std::this_thread::sleep_for(std::chrono::seconds(5));
    }
}
