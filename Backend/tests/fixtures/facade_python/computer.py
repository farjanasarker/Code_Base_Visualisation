class CPU:
    def freeze(self):
        pass

    def jump(self, position):
        pass

    def execute(self):
        pass


class Memory:
    def load(self, position, data):
        pass


class HardDrive:
    def read(self, lba, size):
        pass


class Monitor:
    def display(self):
        pass


class Keyboard:
    def poll(self):
        pass


class ComputerFacade:
    def __init__(self):
        self.cpu = CPU()
        self.memory = Memory()
        self.hard_drive = HardDrive()
        self.monitor = Monitor()
        self.keyboard = Keyboard()

    def start(self):
        self.cpu.freeze()
        self.memory.load(0, [])
        self.hard_drive.read(0, 0)
        self.cpu.jump(0)
        self.cpu.execute()
        self.monitor.display()
        self.keyboard.poll()
