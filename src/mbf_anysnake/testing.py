import re
import multiprocessing
import time
import shutil
from pathlib import Path


def run_tests(modules, dockerator, config, report_only=False):
    all_modules = discover_modules(dockerator.paths["code"])
    if not modules:
        modules = all_modules
    else:
        for k in modules:
            if k not in all_modules:
                raise ValueError("module not found", k)
    print("run tests on", modules)
    output_dir = Path(config["base"].get("test_result_dir", "test_results"))
    output_dir.mkdir(exist_ok=True)
    (output_dir / "html").mkdir(exist_ok=True)
    error_dir = output_dir / "with_errors"
    if error_dir.exists():
        shutil.rmtree(error_dir)
    error_dir.mkdir()
    print("output results to", output_dir)
    if not report_only:
        multiplex_tests(modules, output_dir, dockerator, config)
    report_tests(modules, output_dir)


def discover_modules(code_path):
    res = []
    for d in Path(code_path).glob("*"):
        if d.is_dir():
            conf_test_path = d / "tests" / "conftest.py"
            if conf_test_path.exists():
                res.append(d.name)
    return res


def multiplex_tests(modules, output_dir, dockerator, config):
    cmds = [
        (
            f"cd /project/code/{module} && pytest --junitxml=/project/{output_dir}/{module}.log --html=/project/{output_dir}/html/{module}.html",
            dockerator,
            config,
            ii,
        )
        for ii, module in enumerate(modules)
    ]
    p = multiprocessing.Pool(multiprocessing.cpu_count())
    results = p.map(run_single_test, cmds)
    p.close()
    p.join()
    output = ""
    for m, results in zip(modules, results):
        if isinstance(results, tuple):
            results = results[0].decode("utf-8") + "\n" + results[1].decode("utf-8")
        else:
            results.decode("utf-8")
        print(m, results)
        output += f"Module: {m}\n{results}\n\n\n"
    (output_dir / "test_results.txt").write_text(output.replace("\r\n", "\n"))
    print("Test results written to %s" % ((output_dir / "test_results.txt",)))


def report_tests(modules, output_dir):
    for m in modules:
        html_filename = output_dir / "html" / (m + ".html")
        if contained_errors(html_filename):
            target = (output_dir / "with_errors" / (m + ".html"))
            target.symlink_to(html_filename.absolute())
            any_errors = True
    if any_errors:
        target  = target = (output_dir / "with_errors" / 'assets')
        target.symlink_to((output_dir / "html" / 'assets').absolute(), True)




def run_single_test(args):
    cmd, dockerator, config, ii = args
    from .cli import home_files, get_volumes_config

    time.sleep(0.01 * ii)
    return dockerator.run_non_interactive(
        cmd,
        allow_writes=False,
        home_files=home_files,
        volumes_ro=get_volumes_config(config, "run", "additional_volumes_ro"),
        volumes_rw=get_volumes_config(config, "run", "additional_volumes_rw"),
    )


def contained_errors(html_filename):
    source = html_filename.read_text()
    failed = re.findall(r">(\d+) failed", source)
    errors = re.findall(r">(\d+) errors", source)
    unexpected_passes = re.findall(r">(\d+) unexpected passes", source)
    combined = failed + errors + unexpected_passes
    combined = [int(x) for x in combined if int(x) > 0]
    return bool(combined)
