import ast
import collections
import mmap
import pathlib
import random
import shutil
import string
import subprocess
import unittest

from graminelibos.regression import (
    HAS_EDMM,
    HAS_SGX,
    ON_X86,
    RegressionTestCase,
)


class TC_00_Basic(RegressionTestCase):
    def test_001_path_normalization(self):
        _, stderr = self.run_binary(['normalize_path'])

        self.assertIn("Success!\n", stderr)

    def test_002_avl_tree(self):
        _, _ = self.run_binary(['avl_tree_test'])

    def test_003_printf(self):
        _, stderr = self.run_binary(['printf_test'])
        self.assertIn("TEST OK", stderr)

    def test_004_strtoll(self):
        _, stderr = self.run_binary(['strtoll_test'])
        self.assertIn("TEST OK", stderr)


class TC_00_BasicSet2(RegressionTestCase):
    @unittest.skipUnless(ON_X86, "x86-specific")
    def test_Exception2(self):
        _, stderr = self.run_binary(['Exception2'])
        self.assertIn('Enter Main Thread', stderr)
        self.assertIn('failure in the handler: 0x', stderr)
        self.assertNotIn('Leave Main Thread', stderr)

    def test_File2(self):
        _, stderr = self.run_binary(['File2'])
        self.assertIn('Enter Main Thread', stderr)
        self.assertIn('Hello World', stderr)
        self.assertIn('Leave Main Thread', stderr)

    def test_HelloWorld(self):
        stdout, _ = self.run_binary(['HelloWorld'])
        self.assertIn('Hello World', stdout)

    def test_Pie(self):
        stdout, stderr = self.run_binary(['Pie'])
        self.assertIn('start program: Pie', stderr)
        self.assertIn('Hello World', stdout)

    @unittest.skipIf(HAS_SGX, "Pipes must be created in two parallel threads under SGX")
    def test_Process4(self):
        _, stderr = self.run_binary(['Process4'], timeout=5)
        self.assertRegex(stderr, r'In process: .*Process4')
        self.assertIn('wall time = ', stderr)
        for i in range(100):
            self.assertIn('In process: Process4 %d ' % i, stderr)

    @unittest.skipUnless(ON_X86, "x86-specific")
    def test_Segment(self):
        _, stderr = self.run_binary(['Segment'])
        self.assertIn('Test OK', stderr)


class TC_01_Bootstrap(RegressionTestCase):
    def test_100_basic_boostrapping(self):
        _, stderr = self.run_binary(['Bootstrap'])

        # Basic Bootstrapping
        self.assertIn('User Program Started', stderr)

        # One Argument Given
        self.assertIn('# of Arguments: 1', stderr)
        self.assertRegex(stderr, r'argv\[0\] = .*Bootstrap')

        # Control Block: Debug Stream (Inline)
        self.assertIn('Written to Debug Stream', stderr)

        # Control Block: Allocation Alignment
        self.assertIn('Allocation Alignment: {}'.format(mmap.ALLOCATIONGRANULARITY), stderr)

    def test_101_basic_boostrapping_five_arguments(self):
        _, stderr = self.run_binary(['Bootstrap', 'a', 'b', 'c', 'd'])

        # Five Arguments Given
        self.assertIn('# of Arguments: 5', stderr)
        self.assertIn('argv[1] = a', stderr)
        self.assertIn('argv[2] = b', stderr)
        self.assertIn('argv[3] = c', stderr)
        self.assertIn('argv[4] = d', stderr)

    def test_102_cpuinfo(self):
        with open('/proc/cpuinfo') as file_:
            cpuinfo = file_.read().strip().split('\n\n')[-1]
        cpuinfo = dict(map(str.strip, line.split(':'))
            for line in cpuinfo.split('\n'))

        _, stderr = self.run_binary(['Bootstrap'])

        self.assertIn('CPU num: {}'.format(int(cpuinfo['processor']) + 1),
            stderr)
        self.assertIn('CPU vendor: {[vendor_id]}'.format(cpuinfo), stderr)
        self.assertIn('CPU brand: {[model name]}'.format(cpuinfo), stderr)
        self.assertIn('CPU family: {[cpu family]}'.format(cpuinfo), stderr)
        self.assertIn('CPU model: {[model]}'.format(cpuinfo), stderr)
        self.assertIn('CPU stepping: {[stepping]}'.format(cpuinfo), stderr)

    def test_103_dotdot(self):
        _, stderr = self.run_binary(['..Bootstrap'])
        self.assertIn('User Program Started', stderr)

    @unittest.skipUnless(HAS_SGX, 'this test requires SGX')
    def test_120_8gb_enclave(self):
        _, stderr = self.run_binary(['Bootstrap6'], timeout=360)
        self.assertIn('Memory Address Range OK', stderr)

    def test_130_large_number_of_items_in_manifest(self):
        _, stderr = self.run_binary(['Bootstrap7'])
        self.assertIn('key1=na', stderr)
        self.assertIn('key1000=batman', stderr)

    def test_140_missing_executable_and_manifest(self):
        try:
            _, stderr = self.run_binary(['fakenews'])
            self.fail(
                'expected non-zero returncode, stderr: {!r}'.format(stderr))
        except subprocess.CalledProcessError:
            pass

class TC_02_Symbols(RegressionTestCase):
    ALL_SYMBOLS = [
        'PalVirtualMemoryAlloc',
        'PalVirtualMemoryFree',
        'PalVirtualMemoryProtect',
        'PalSetMemoryBookkeepingUpcalls',
        'PalProcessCreate',
        'PalProcessExit',
        'PalStreamOpen',
        'PalStreamWaitForClient',
        'PalStreamRead',
        'PalStreamWrite',
        'PalStreamDelete',
        'PalStreamMap',
        'PalStreamUnmap',
        'PalStreamSetLength',
        'PalStreamFlush',
        'PalSendHandle',
        'PalReceiveHandle',
        'PalStreamAttributesQuery',
        'PalStreamAttributesQueryByHandle',
        'PalStreamAttributesSetByHandle',
        'PalStreamChangeName',
        'PalThreadCreate',
        'PalThreadYieldExecution',
        'PalThreadExit',
        'PalThreadResume',
        'PalSetExceptionHandler',
        'PalEventCreate',
        'PalEventSet',
        'PalEventClear',
        'PalEventWait',
        'PalStreamsWaitEvents',
        'PalObjectClose',
        'PalSystemTimeQuery',
        'PalRandomBitsRead',
    ]
    if ON_X86:
        ALL_SYMBOLS.append('PalSegmentBaseGet')
        ALL_SYMBOLS.append('PalSegmentBaseSet')

    def test_000_symbols(self):
        _, stderr = self.run_binary(['Symbols'])
        prefix = 'symbol: '
        found_symbols = dict(line[len(prefix):].split(' = ')
            for line in stderr.strip().split('\n') if line.startswith(prefix))
        self.assertCountEqual(found_symbols, self.ALL_SYMBOLS)
        for k, value in found_symbols.items():
            value = ast.literal_eval(value)
            self.assertNotEqual(value, 0, 'symbol {} has value 0'.format(k))

class TC_10_Exception(RegressionTestCase):
    def is_altstack_different_from_main_stack(self, output):
        mainstack = 0
        altstack = 0
        for line in output.splitlines():
            if line.startswith('Stack in main:'):
                mainstack = int(line.split(':')[1], 0)
            elif line.startswith('Stack in handler:'):
                altstack = int(line.split(':')[1], 0)

        # handler stack cannot be "close" to the main stack
        if abs(mainstack - altstack) < 8192:
            return False
        return True

    @unittest.skipUnless(ON_X86, "x86-specific")
    def test_000_exception(self):
        _, stderr = self.run_binary(['Exception'])

        self.assertTrue(self.is_altstack_different_from_main_stack(stderr))

        # Exception Handling (Div-by-Zero)
        self.assertIn('Arithmetic Exception Handler', stderr)

        # Exception Handling (Memory Fault)
        self.assertIn('Memory Fault Exception Handler', stderr)

        # Exception Handler Swap
        self.assertIn('Arithmetic Exception Handler 1', stderr)
        self.assertIn('Arithmetic Exception Handler 2', stderr)

        # Exception Handling (Set Context)
        self.assertIn('Arithmetic Exception Handler 1', stderr)

        # Exception Handling (Red zone)
        self.assertIn('Red zone test ok.', stderr)

class TC_20_SingleProcess(RegressionTestCase):
    def test_000_exit_code(self):
        with self.expect_returncode(112):
            self.run_binary(['Exit'])

    def test_100_file(self):
        try:
            pathlib.Path('file_nonexist.tmp').unlink()
        except FileNotFoundError:
            pass
        pathlib.Path('file_delete.tmp').touch()

        with open('File.manifest', 'rb') as file_:
            file_exist = file_.read()

        _, stderr = self.run_binary(['File'])

        # Basic File Opening
        self.assertIn('File Open Test 1 OK', stderr)
        self.assertIn('File Open Test 2 OK', stderr)
        self.assertIn('File Open Test 3 OK', stderr)

        # Basic File Creation
        self.assertIn('File Creation Test 1 OK', stderr)
        self.assertIn('File Creation Test 2 OK', stderr)
        self.assertIn('File Creation Test 3 OK', stderr)

        # File Reading
        self.assertIn('Read Test 1 (0th - 40th): {}'.format(
            file_exist[0:40].hex()), stderr)
        self.assertIn('Read Test 2 (0th - 40th): {}'.format(
            file_exist[0:40].hex()), stderr)
        self.assertIn('Read Test 3 (200th - 240th): {}'.format(
            file_exist[200:240].hex()), stderr)

        # File Writing
        with open('file_nonexist.tmp', 'rb') as file_:
            file_nonexist = file_.read()

        self.assertEqual(file_exist[0:40], file_nonexist[200:240])
        self.assertEqual(file_exist[200:240], file_nonexist[0:40])

        # File Attribute Query
        self.assertIn('Query: type = ', stderr)
        self.assertIn(', size = {}'.format(len(file_exist)), stderr)

        # File Attribute Query by Handle
        self.assertIn('Query by Handle: type = ', stderr)
        self.assertIn(', size = {}'.format(len(file_exist)), stderr)

        # File Mapping
        self.assertIn(
            'Map Test 1 (0th - 40th): {}'.format(file_exist[0:40].hex()),
            stderr)
        self.assertIn(
            'Map Test 2 (200th - 240th): {}'.format(file_exist[200:240].hex()),
            stderr)

        # Set File Length
        self.assertEqual(
            pathlib.Path('file_nonexist.tmp').stat().st_size,
            mmap.ALLOCATIONGRANULARITY)

        # File Deletion
        self.assertFalse(pathlib.Path('file_delete.tmp').exists())

    def test_110_directory(self):
        for path in ['dir_exist.tmp', 'dir_nonexist.tmp', 'dir_delete.tmp',
                     'dir_rename.tmp', 'dir_rename_delete.tmp']:
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                pass

        path = pathlib.Path('dir_exist.tmp')
        files = [path / ''.join(random.choice(string.ascii_letters)
                                for _ in range(8))
                 for _ in range(5)]
        path.mkdir()
        for file_ in files:
            file_.touch()
        pathlib.Path('dir_delete.tmp').mkdir()

        _, stderr = self.run_binary(['Directory'])

        # Basic Directory Opening
        self.assertIn('Directory Open Test 1 OK', stderr)
        self.assertIn('Directory Open Test 2 OK', stderr)
        self.assertIn('Directory Open Test 3 OK', stderr)

        # Basic Directory Creation
        self.assertIn('Directory Creation Test 1 OK', stderr)
        self.assertIn('Directory Creation Test 2 OK', stderr)
        self.assertIn('Directory Creation Test 3 OK', stderr)

        # Directory Reading
        for file_ in files:
            self.assertIn('Read Directory: {}'.format(file_.name), stderr)

        # Directory Attribute Query
        self.assertIn('Query: type = ', stderr)

        # Directory Attribute Query by Handle
        self.assertIn('Query by Handle: type = ', stderr)

        # Directory Deletion
        self.assertFalse(pathlib.Path('dir_delete.tmp').exists())
        self.assertFalse(pathlib.Path('dir_rename.tmp').exists())
        self.assertFalse(pathlib.Path('dir_rename_delete.tmp').exists())

    def test_200_event(self):
        _, stderr = self.run_binary(['Event'])
        self.assertIn('TEST OK', stderr)

    def test_300_memory(self):
        if not HAS_SGX or HAS_EDMM:
            _, stderr = self.run_binary(['memory'])
            self.assertIn('TEST OK', stderr)
        else:
            # SGX1 does not support unmapping a page or changing its permission after enclave init.
            # Therefore the memory protection and deallocation tests will fail.
            try:
                self.run_binary(['memory'])
                self.fail('expected to return nonzero')
            except subprocess.CalledProcessError as e:
                self.assertEqual(e.returncode, 1)
                stderr = e.stderr.decode()
                self.assertRegex(stderr, r'write to R mem at 0x[0-9a-f]+ unexpectedly succeeded')

    def test_400_pipe(self):
        _, stderr = self.run_binary(['Pipe'])

        # Pipe Creation
        self.assertIn('Pipe Creation 1 OK', stderr)

        # Pipe Attributes
        self.assertIn('Pipe Attribute Query 1 on pipesrv returned OK', stderr)

        # Pipe Connection
        self.assertIn('Pipe Connection 1 OK', stderr)

        # Pipe Transmission
        self.assertIn('Pipe Write 1 OK', stderr)
        self.assertIn('Pipe Read 1: Hello World 1', stderr)
        self.assertIn('Pipe Write 2 OK', stderr)
        self.assertIn('Pipe Read 2: Hello World 2', stderr)

    @unittest.skipUnless(ON_X86, "x86-specific")
    def test_500_thread(self):
        _, stderr = self.run_binary(['Thread'])

        # Thread Creation
        self.assertIn('Child Thread Created', stderr)
        self.assertIn('Run in Child Thread: Hello World', stderr)

        # Multiple Threads Run in Parallel
        self.assertIn('Threads Run in Parallel OK', stderr)

        # Set Thread Private Segment Register
        self.assertIn('Private Message (FS Segment) 1: Hello World 1', stderr)
        self.assertIn('Private Message (FS Segment) 2: Hello World 2', stderr)

        # Thread Exit
        self.assertIn('Child Thread Exited', stderr)

    def test_510_thread2(self):
        _, stderr = self.run_binary(['Thread2'])

        # Thread Cleanup: Exit by return.
        self.assertIn('Thread 2 ok.', stderr)

        # Thread Cleanup: Exit by PalThreadExit.
        self.assertIn('Thread 3 ok.', stderr)
        self.assertNotIn('Exiting thread 3 failed.', stderr)

        # Thread Cleanup: Can still start threads.
        self.assertIn('Thread 4 ok.', stderr)

    @unittest.skipUnless(HAS_SGX, 'This test is only meaningful on SGX PAL')
    def test_511_thread2_exitless(self):
        _, stderr = self.run_binary(['Thread2_exitless'], timeout=60)

        # Thread Cleanup: Exit by return.
        self.assertIn('Thread 2 ok.', stderr)

        # Thread Cleanup: Exit by PalThreadExit.
        self.assertIn('Thread 3 ok.', stderr)
        self.assertNotIn('Exiting thread 3 failed.', stderr)

        # Thread Cleanup: Can still start threads.
        self.assertIn('Thread 4 ok.', stderr)

    def test_900_misc(self):
        _, stderr = self.run_binary(['Misc'])
        # Query System Time
        self.assertIn('Query System Time OK', stderr)

        # Delay Execution for 10000 Microseconds
        self.assertIn('Delay Execution for 10000 Microseconds OK', stderr)

        # Delay Execution for 3 Seconds
        self.assertIn('Delay Execution for 3 Seconds OK', stderr)

        # Generate Random Bits
        self.assertIn('Generate Random Bits OK', stderr)

    def test_910_hex(self):
        _, stderr = self.run_binary(['Hex'])
        # Hex 2 String Helper Function
        self.assertIn('Hex test 1 is deadbeef', stderr)
        self.assertIn('Hex test 2 is cdcdcdcdcdcdcdcd', stderr)

class TC_21_ProcessCreation(RegressionTestCase):
    def test_100_process(self):
        _, stderr = self.run_binary(['Process'], timeout=60)
        counter = collections.Counter(stderr.split('\n'))
        # Process Creation
        self.assertEqual(counter['Child Process Created'], 3)

        # Process Creation Arguments
        self.assertEqual(counter['argv[0] = Process'], 3)
        self.assertEqual(counter['argv[1] = Child'], 3)

        # Process Channel Transmission
        self.assertEqual(counter['Process Write 1 OK'], 3)
        self.assertEqual(counter['Process Read 1: Hello World 1'], 3)
        self.assertEqual(counter['Process Write 2 OK'], 3)
        self.assertEqual(counter['Process Read 2: Hello World 2'], 3)

class TC_23_SendHandle(RegressionTestCase):
    def test_000_send_handle(self):
        _, stderr = self.run_binary(['send_handle'])
        self.assertIn('Parent: test OK', stderr)
        self.assertIn('Child: test OK', stderr)

class TC_30_IPParser(RegressionTestCase):
    def test_000_ipv4(self):
        _, stderr = self.run_binary(['ipv4_parser'])
        self.assertIn('TEST OK', stderr)

    def test_010_ipv6(self):
        _, stderr = self.run_binary(['ipv6_parser'])
        self.assertIn('TEST OK', stderr)

@unittest.skipUnless(HAS_SGX, 'This test is only meaningful on SGX PAL')
class TC_50_Attestation(RegressionTestCase):
    def test_000_attestation_report(self):
        _, stderr = self.run_binary(['AttestationReport'])
        self.assertNotIn('ERROR', stderr)
        self.assertIn('Success', stderr)
