import array

__all__ = ["BonelessSimulator"]


# Used to calculate sign bit and also
# overflow.
def sign(val):
    return int((val & 0x08000) != 0)


class BonelessSimulator:
    def __init__(self, start_pc=0x10, memsize=1024, io_callback=None):
        def memset():
            for i in range(memsize):
                yield 0

        self.sim_active = False
        self.window = 0
        self.pc = start_pc
        self.flags = { "Z" : 0, "S" : 0, "C" : 0, "V" : 0}
        self.mem = array.array("H", memset())
        self.io_callback = io_callback

    def __enter__(self):
        self.sim_active = True
        return self

    def __exit__(self, type, value, traceback):
        self.sim_active = False

    def regs(self):
        return self.mem[self.window:self.window+16]

    def read_reg(self, reg):
        return self.mem[self.reg_loc(reg)]

    def reg_loc(self, offs):
        return self.window + offs

    def set_pc(self, new_pc):
        if not self.sim_active:
            self.pc = new_pc

    def write_reg(self, reg, val):
        if not self.sim_active:
            self.mem[self.reg_loc(reg)] = val

    def load_program(self, contents, start=0x10):
        if not self.sim_active:
            for i, c in enumerate(contents):
                self.mem[i + start] = c

    # Replace the currently-defined I/O callback with a new one.
    # I/O callback has the following signature:
    # fn(addr, write=False). Reads return read value.
    # Writes return anything (including None), return value ignored.
    def register_io(self, callback):
        """Replace the currently-defined I/O callback with a new one.

        The I/O callback has the following signature:
        ``fn(addr, data=None)``, where `addr` is the I/O address to read/write,
        and `data` is the data to write, `None` is this I/O access is a read.
        Reads return value read from I/O device. Writes return None, return
        value ignored.
        """
        if not self.sim_active:
            self.io_callback = callback

    def stepi(self):
        opcode = self.mem[self.pc]
        op_class = (0xF800 & opcode) >> 11

        if op_class in [0x00, 0x01]:
            self.do_a_class(opcode)
            self.pc = self.pc + 1
        elif op_class in [0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]:
            self.do_i_class(opcode)
            self.pc = self.pc + 1
        else:
            raise NotImplementedError("Step Instruction")

    # Utility Functions- Do not call directly
    def _write_reg(self, reg, val):
        self.mem[self.reg_loc(reg)] = val

    # Handle Opcode Clases- Do not call directly
    def do_a_class(self, opcode):
        dst = (0x0700 & opcode) >> 8
        opa = (0x00E0 & opcode) >> 5
        opb = (0x001C & opcode) >> 2
        typ = (0x0003 & opcode)
        code = (0x0800 & opcode) >> 11

        val_a = self.read_reg(opa)
        val_b = self.read_reg(opb)
        s_a = sign(val_a)
        s_b = sign(val_b)

        if code and (typ in range(3)):
            # ADD
            if typ == 0x00:
                raw = val_a + val_b
                s_r = sign(raw)

                self.flags["C"] = int(raw > 65535)
                # http://teaching.idallen.com/dat2343/10f/notes/040_overflow.txt
                self.flags["V"] = int((s_a and s_b and not s_r) or (not s_a and not s_b and s_r))

                # Bring raw back into range.
                if self.flags["C"]:
                    self._write_reg(dst, raw - 65536)
                else:
                    self._write_reg(dst, raw)
            # SUB/CMP
            else:
                raw = val_a - val_b
                s_r = sign(raw)

                self.flags["C"] = int(val_a < val_b)
                self.flags["V"] = int((s_a and not s_b and not s_r) or (not s_a and s_b and s_r))

                # CMP skips writing results
                if typ == 0x01:
                    # Bring raw back into range
                    if raw < 0:
                        self._write_reg(dst, raw + 65536)
                    else:
                        self._write_reg(dst, raw)
        elif not code and typ in range(3):
            if typ == 0x00:
                raw = val_a & val_b
            elif typ == 0x01:
                raw = val_a | val_b
            else:
                raw = val_a ^ val_b
            self._write_reg(dst, raw)
        else:
            raise NotImplementedError("Do A Class")

        self.flags["Z"] = (raw == 0)
        self.flags["S"] = sign(raw)

    def do_i_class(self, opcode):
        opc = (0x3800 & opcode) >> 11
        srcdst = (0x0700 & opcode) >> 8
        imm = (0x00FF & opcode)

        if opc == 0x00:
            val = (self.read_reg(srcdst) & 0xFF00) | imm
        elif opc == 0x01:
            val = (self.read_reg(srcdst) & 0x00FF) | imm
        else:
            raise NotImplementedError("Do I Class")

        self._write_reg(srcdst, val)
