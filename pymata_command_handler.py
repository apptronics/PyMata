__author__ =  'Copyright (c) 2013 Alan Yorinks All rights reserved.'

"""
Copyright (c) 2013 Alan Yorinks All rights reserved.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU  General Public
License as published by the Free Software Foundation; either
version 3 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this library; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""

import threading



class PyMataCommandHandler(threading.Thread):
    """
    This class handles all data interchanges with Firmata
    The receive loop runs in its own thread.

    Messages to be sent to Firmata are queued through a deque to allow for priority
    messages to take precedence. The deque is checked within the receive loop for any
    outgoing messages.

    There is no blocking in either communications direction.

    There is blocking when accessing the data tables through the _data_lock
    """

    # the following defines are from Firmata.h

    # message command bytes (128-255/ 0x80- 0xFF)
    # from this client to firmata
    MSG_CMD_MIN = 0x80  # minimum value for a message from firmata
    REPORT_ANALOG = 0xC0  # enable analog input by pin #
    REPORT_DIGITAL = 0xD0  # enable digital input by port pair
    SET_PIN_MODE = 0xF4  # set a pin to INPUT/OUTPUT/PWM/etc
    START_SYSEX = 0xF0  # start a MIDI Sysex message
    END_SYSEX = 0xF7  # end a MIDI Sysex message
    SYSTEM_RESET = 0xFF  # reset from MIDI

    # messages from firmata
    DIGITAL_MESSAGE = 0x90  # send or receive data for a digital pin
    ANALOG_MESSAGE = 0xE0  # send or receive data for a PWM configured pin
    REPORT_VERSION = 0xF9  # report protocol version

    # user defined SYSEX commands
    # from this client
    ENCODER_CONFIG = 0x20  # create and enable encoder object
    TONE_PLAY = 0x22  # play a tone at a specified frequency and duration

    # messages from firmata
    ENCODER_DATA = 0x21 # current encoder position data

    # standard sysex commands

    SERVO_CONFIG = 0x70     # set servo pin and max and min angles
    STRING_DATA = 0x71 #  a string message with 14-bits per char
    REPORT_FIRMWARE = 0x79  # report name and version of the firmware
    SAMPLING_INTERVAL = 0x7A  # modify the sampling interval

    # reserved values
    SYSEX_NON_REALTIME = 0x7E  # MIDI Reserved for non-realtime messages
    SYSEX_REALTIME = 0x7F  # MIDI Reserved for realtime messages


    # pin modes
    INPUT = 0x00
    OUTPUT = 0x01
    ANALOG = 0x02  # analog pin in analogInput mode
    PWM = 0x03  # digital pin in PWM output mode
    SERVO = 0x04  # digital pin in Servo output mode
    SHIFT = 0x05  # shiftIn/shiftOut mode
    I2C = 0x06  # pin included in I2C setup
    ENCODER = 0x07  # Analog pin output pin in ENCODER mode
    TONE = 0x08  # Any pin in TONE mode

    # The response tables hold response information for all pins
    # Each table is a table of entries for each pin, which consists of the pin mode, and its last value from firmata

    # This is a table that stores digital pin modes and data
    # each entry represents  its mode (INPUT or OUTPUT, PWM, SERVO, ENCODER), and its last current value
    digital_response_table = []

    # This is a table that stores analog pin modes and data
    # each entry represents ia mode (INPUT or OUTPUT), and its last current value
    analog_response_table = []

    # These values are indexes into the response table entries
    RESPONSE_TABLE_MODE = 0
    RESPONSE_TABLE_PIN_DATA_VALUE = 1

    # These values are the index into the data passed by _arduino and used to reassemble integer values
    MSB = 2
    LSB = 1

    # This is a map that allows the look up of command handler methods using a command as the key.
    # This is populated in the run method after the python interpreter sees all of the command handler method
    # defines (python does not have forward referencing)

    # The "key" is the command, and the value contains is a list containing the  method name and the number of
    # parameter bytes that the method will require to process the message
    command_dispatch = {}

    # this deque is used by the methods that assemble messages to be sent to Firmata. The deque is filled outside of
    # of the message processing loop and emptied within the loop.
    command_deque = None

    # firmata version information - saved as a list - [major, minor]
    firmata_version = []

    # firmata firmware version information saved as a list [major, minor, file_name]
    firmata_firmware = []

    # a lock to protect the data tables when they are being accessed
    data_lock = None

    # number of pins defined by user for the _arduino board
    number_digital_pins = 0
    number_analog_pins = 0

    def __init__(self, transport, command_deque, data_lock,
                 number_digital_pins, number_analog_pins):
        """
        constructor for CommandHandler class
        @param transport: A reference to the ommunications port designator.
        @param command_deque:  A reference to a command deque.
        @param data_lock: A reference to a thread lock.
        @param number_digital_pins: Number of digital pins to track in digital response table.
        @param number_analog_pins: Number of analog pins to track in analog response table.
        """

        # response table initialization
        # for each pin set the mode to input and the last read data value to zero
        for pin in range(0, number_digital_pins):
            response_entry = [self.INPUT, 0]
            self.digital_response_table.append(response_entry)

        for pin in range(0, number_analog_pins):
            response_entry = [self.INPUT, 0]
            self.analog_response_table.append(response_entry)
        self.data_lock = data_lock

        self.number_digital_pins = number_digital_pins
        self.number_analog_pins = number_analog_pins

        self.transport = transport
        self.command_deque = command_deque
        threading.Thread.__init__(self)
        self.daemon = True


    #
    # methods to handle messages received from Firmata
    #
    def report_version(self, data):
        """
        This method processes the report version message,  sent asynchronously by Firmata when it starts up
        NOTE: This message is never received for a Leonardo.

        Use the api method api_get_version to retrieve this information
        @param data: Message data from Firmata
        @return: No return value.
        """
        self.firmata_version.append(data[0])  # add major
        self.firmata_version.append(data[1])  # add minor

    def report_firmware(self, data):
        """
        This method processes the report firmware message,  sent asynchronously by Firmata when it starts up
        NOTE: This message is never received for a Leonardo.
        
        Use the api method api_get_firmware_version to retrieve this information
        @param data: Message data from Firmata
        @return: No return value.
        """

        self.firmata_firmware.append(data[0])  # add major
        self.firmata_firmware.append(data[1])  # add minor

        # extract the file name string from the message
        # file name is in bytes 2 to the end
        name_data = data[2:]

        # constructed file name
        file_name = []

        # the file name is passed in with each character as 2 bytes, the high order byte is equal to 0
        # so skip over these zero bytes
        for i in name_data[::2]:
            file_name.append(chr(i))

        # add filename to tuple
        self.firmata_firmware.append("".join(file_name))

    def analog_message(self, data):
        """
        This method handles the incoming analog data message.
        It stores the data value for the pin in the analog response table
        @param data: Message data from Firmata
        @return: No return value.        """

        self.data_lock.acquire(True)
        # convert MSB and LSB into an integer
        self.analog_response_table[data[self.RESPONSE_TABLE_MODE]][self.RESPONSE_TABLE_PIN_DATA_VALUE] \
            = (data[self.MSB] << 7) + data[self.LSB]
        self.data_lock.release()

    def digital_message(self, data):
        """
        This method handles the incoming digital message.
        It stores the data values in the digital response table.
        Data is stored for all 8 bits of a  digital port
        @param data: Message data from Firmata
        @return: No return value.
        """
        port = data[0]
        port_data = (data[self.MSB] << 7) + data[self.LSB]

        # set all the pins for this reporting port
        # get the first pin number for this report
        pin = port * 8
        for pin in range(pin, pin + 8):
            # shift through all the bit positions and set the digital response table
            self.data_lock.acquire(True)
            self.digital_response_table[pin][self.RESPONSE_TABLE_PIN_DATA_VALUE] = port_data & 0x01
            self.data_lock.release()
            # get the next data bit
            port_data >>= 1

    def encoder_data(self, data):
        """
        This method handles the incoming encoder data message and stores
        the data in the response table.
        @param data: Message data from Firmata
        @return: No return value.
        """
        val = int((data[self.MSB] << 7) + data[self.LSB])
        # set value so that it shows positive and negative values
        if val > 8192:
            val -= 16384
        self.data_lock.acquire(True)
        self.digital_response_table[data[self.RESPONSE_TABLE_MODE]][self.RESPONSE_TABLE_PIN_DATA_VALUE] = val
        self.data_lock.release()


    def get_analog_response_table(self):
        """
        This method returns the entire analog response table to the caller
        @return: The analog response table.
        """
        self.data_lock.acquire(True)
        data = self.analog_response_table
        self.data_lock.release()
        return data

    def get_digital_response_table(self):
        """
        This method returns the entire digital response table to the caller
        @rtype : The digital response table.
        """
        self.data_lock.acquire(True)
        data = self.digital_response_table
        self.data_lock.release()
        return data


    def send_sysex(self, sysex_command, sysex_data=None):
        """
        This method will send a Sysex command to Firmata with any accompanying data

        @param sysex_command: sysex command
        @param sysex_data: data for command
        @rtype : No return value.
        """
        if not sysex_data:
            sysex_data = []

        # convert the message command and data to characters
        sysex_message = chr(self.START_SYSEX)
        sysex_message += chr(sysex_command)
        if len(sysex_data):
            for d in sysex_data:
                sysex_message += chr(d)
        sysex_message += chr(self.END_SYSEX)

        for data in sysex_message:
            self.transport.write(data)

    def send_command(self, command):
        """
        This method is used to transmit a non-sysex command.
        @param command: Command to send to firmata includes command + data formatted by caller
        @rtype : No return value.
        """
        send_message = ""
        for i in command:
            send_message += chr(i)

        for data in send_message:
            self.transport.write(data)

    def system_reset(self):
        """
        Send the reset command to the Arduino.
        It resets the response tables to their initial values
        @rtype : No return value
        """
        data = chr(self.SYSTEM_RESET)
        self.transport.write(data)

        # response table re-initialization
        # for each pin set the mode to input and the last read data value to zero
        self.data_lock.acquire(True)

        # remove all old entries from existing tables
        for _ in range(len(self.digital_response_table)):
            self.digital_response_table.pop()

        for _ in range(len(self.analog_response_table)):
            self.analog_response_table.pop()

        # reinitialize tables
        for pin in range(0, self.number_digital_pins):
            response_entry = [self.INPUT, 0]
            self.digital_response_table.append(response_entry)

        for pin in range(0, self.number_analog_pins):
            response_entry = [self.INPUT, 0]
            self.analog_response_table.append(response_entry)

        self.data_lock.release()


    #noinspection PyMethodMayBeStatic
    # keeps pycharm happy
    def _string_data(self, data):
        """
        This method handles the incoming string data message from Firmata.
        The string is printed to the consolse

        @param data: Message data from Firmata
        @rtype : No return value.s
        """
        print "_string_data:"
        string_to_print = []
        for i in data[::2]:
            string_to_print.append(chr(i))

        print string_to_print


    def run(self):
        """
        This method starts the thread that continuously runs to receive and interpret
        messages coming from Firmata. This must be the last method in this file

        It also checks the deque for messages to be sent to Firmata.
        """

        # To add a command to the command dispatch table, append here.
        self.command_dispatch.update({self.REPORT_VERSION: [self.report_version, 2]})
        self.command_dispatch.update({self.REPORT_FIRMWARE: [self.report_firmware, 1]})
        self.command_dispatch.update({self.ANALOG_MESSAGE: [self.analog_message, 2]})
        self.command_dispatch.update({self.DIGITAL_MESSAGE: [self.digital_message, 2]})
        self.command_dispatch.update({self.ENCODER_DATA: [self.encoder_data, 3]})
        self.command_dispatch.update({self.STRING_DATA: [self._string_data, 2]})

        while 1:  # a forever loop
            if len(self.command_deque):
                # get next byte from the deque and process it
                data = self.command_deque.popleft()

                # this list will be populated with the received data for the command
                command_data = []

                # process sysex commands
                if data == self.START_SYSEX:
                    # next char is the actual sysex command
                    # wait until we can get data from the deque
                    while len(self.command_deque) == 0:
                        pass
                    sysex_command = self.command_deque.popleft()

                    # retrieve the associated command_dispatch entry for this command
                    dispatch_entry = self.command_dispatch.get(sysex_command)

                    # get a "pointer" to the method that will process this command
                    method = dispatch_entry[0]

                    # now get the rest of the data excluding the END_SYSEX byte
                    end_of_sysex = False
                    while not end_of_sysex:
                        # wait for more data to arrive
                        while len(self.command_deque) == 0:
                            pass
                        data = self.command_deque.popleft()
                        if data != self.END_SYSEX:
                            command_data.append(data)
                        else:
                            end_of_sysex = True

                            # invoke the method to process the command
                            method(command_data)
                        # go to the beginning of the loop to process the next command
                    continue

                #is this a command byte in the range of 0x80-0xff - these are the non-sysex messages
                elif 0x80 <= data <= 0xff:
                    # look up the method for the command in the command dispatch table
                    # for the digital reporting the command value is modified with port number
                    # the handler needs the port to properly process, so decode that from the command and
                    # place in command_data
                    if 0x90 <= data <= 0x9f:
                        port = data & 0xf
                        command_data.append(port)
                        data = 0x90
                    # the pin number for analog data is embedded in the command so, decode it
                    elif 0xe0 <= data <= 0xe9:
                        pin = data & 0xf
                        command_data.append(pin)
                        data = 0xe0
                    else:
                        pass

                    dispatch_entry = self.command_dispatch.get(data)

                    # this calls the method retrieved from the dispatch table
                    method = dispatch_entry[0]

                    # get the number of parameters that this command provides
                    num_args = dispatch_entry[1]

                    #look at the number of args that the selected method requires
                    # now get that number of bytes to pass to the called method
                    for i in range(num_args):
                        while len(self.command_deque) == 0:
                            pass
                        data = self.command_deque.popleft()
                        command_data.append(data)
                        #go execute the command with the argument list
                    method(command_data)

                    # go to the beginning of the loop to process the next command
                    continue






