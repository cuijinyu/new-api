package common

import (
	"bytes"
	"io"
	"os"
)

const defaultBodyStorageDiskThreshold = 1 << 20

type BodyStorage interface {
	io.Reader
	io.Seeker
	io.Closer
	Bytes() ([]byte, error)
	Size() int64
	IsDisk() bool
}

type memoryStorage struct {
	reader *bytes.Reader
	data   []byte
}

func newMemoryStorage(data []byte) *memoryStorage {
	return &memoryStorage{reader: bytes.NewReader(data), data: data}
}

func (s *memoryStorage) Read(p []byte) (int, error) {
	return s.reader.Read(p)
}

func (s *memoryStorage) Seek(offset int64, whence int) (int64, error) {
	return s.reader.Seek(offset, whence)
}

func (s *memoryStorage) Close() error {
	return nil
}

func (s *memoryStorage) Bytes() ([]byte, error) {
	return s.data, nil
}

func (s *memoryStorage) Size() int64 {
	return int64(len(s.data))
}

func (s *memoryStorage) IsDisk() bool {
	return false
}

type diskStorage struct {
	file *os.File
	size int64
}

func newDiskStorage(data []byte) (*diskStorage, error) {
	file, err := os.CreateTemp("", "new-api-body-*")
	if err != nil {
		return nil, err
	}
	if _, err = file.Write(data); err != nil {
		_ = file.Close()
		_ = os.Remove(file.Name())
		return nil, err
	}
	if _, err = file.Seek(0, io.SeekStart); err != nil {
		_ = file.Close()
		_ = os.Remove(file.Name())
		return nil, err
	}
	return &diskStorage{file: file, size: int64(len(data))}, nil
}

func (s *diskStorage) Read(p []byte) (int, error) {
	return s.file.Read(p)
}

func (s *diskStorage) Seek(offset int64, whence int) (int64, error) {
	return s.file.Seek(offset, whence)
}

func (s *diskStorage) Close() error {
	name := s.file.Name()
	err := s.file.Close()
	removeErr := os.Remove(name)
	if err != nil {
		return err
	}
	return removeErr
}

func (s *diskStorage) Bytes() ([]byte, error) {
	if _, err := s.file.Seek(0, io.SeekStart); err != nil {
		return nil, err
	}
	data, err := io.ReadAll(s.file)
	if err != nil {
		return nil, err
	}
	_, err = s.file.Seek(0, io.SeekStart)
	return data, err
}

func (s *diskStorage) Size() int64 {
	return s.size
}

func (s *diskStorage) IsDisk() bool {
	return true
}

func CreateBodyStorage(data []byte) (BodyStorage, error) {
	if len(data) <= defaultBodyStorageDiskThreshold {
		return newMemoryStorage(data), nil
	}
	return newDiskStorage(data)
}

type readerOnly struct {
	reader io.Reader
}

func (r readerOnly) Read(p []byte) (int, error) {
	return r.reader.Read(p)
}

func ReaderOnly(reader io.Reader) io.Reader {
	return readerOnly{reader: reader}
}
