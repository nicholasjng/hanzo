#include <nanobind/nanobind.h>

namespace nb = nanobind;

NB_MODULE(hello_ext, m) {
    m.doc() = "This is a \"hello world\" example with nanobind";
    m.def("say_hello", []() { nb::print("Hello from C++"); });
}
