import os

file_dir = "./files"
for file in os.listdir(file_dir):
    if os.path.getsize(os.path.join(file_dir, file)) > 25 * 1024 * 1024:
        print(f"File {file} is too big, splitting...")
        chunk_id = 1
        with open(os.path.join(file_dir, file), "rb") as f:
            while True:
                data = f.read(25 * 1024 * 1024)
                if not data:
                    break
                with open(os.path.join(file_dir, f"{file}.{chunk_id}.partial"), "wb") as chunk:
                    chunk.write(data)
                    print(f"Chunk {chunk_id} written.")
                chunk_id += 1
