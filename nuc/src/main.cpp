#include "app/App.hpp"
#include "util/Log.hpp"

#include <exception>

int main(int argc, char **argv) {
    try {
        femto::App app;
        return app.run(argc, argv);
    }
    catch(const std::exception &ex) {
        femto::log::stderrError(ex.what());
        return 1;
    }
}
