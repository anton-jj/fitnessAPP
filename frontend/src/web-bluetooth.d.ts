interface BluetoothRemoteGATTCharacteristic extends EventTarget {
  readonly service: BluetoothRemoteGATTService
  readonly uuid: string
  readonly value: DataView | null
  startNotifications(): Promise<BluetoothRemoteGATTCharacteristic>
  stopNotifications(): Promise<BluetoothRemoteGATTCharacteristic>
  readValue(): Promise<DataView>
  writeValue(value: BufferSource): Promise<void>
  addEventListener(type: 'characteristicvaluechanged', listener: (event: Event) => void): void
}

interface BluetoothRemoteGATTService {
  readonly device: BluetoothDevice
  readonly uuid: string
  getCharacteristic(characteristic: string | number): Promise<BluetoothRemoteGATTCharacteristic>
}

interface BluetoothRemoteGATTServer {
  readonly connected: boolean
  connect(): Promise<BluetoothRemoteGATTServer>
  disconnect(): void
  getPrimaryService(service: string | number): Promise<BluetoothRemoteGATTService>
}

interface BluetoothDevice extends EventTarget {
  readonly id: string
  readonly name: string | undefined
  readonly gatt: BluetoothRemoteGATTServer | undefined
}

interface Bluetooth extends EventTarget {
  requestDevice(options: {
    filters?: Array<{ services?: (string | number)[]; name?: string; namePrefix?: string }>
    optionalServices?: (string | number)[]
    acceptAllDevices?: boolean
  }): Promise<BluetoothDevice>
}

interface Navigator {
  bluetooth: Bluetooth
}
