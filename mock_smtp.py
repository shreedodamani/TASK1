import socket
import threading
import sys

def handle_client(client_socket):
    try:
        client_socket.send(b"220 Mock SMTP Server Ready\r\n")
        data_buffer = ""
        in_data = False
        while True:
            line = ""
            while not line.endswith("\r\n"):
                chunk = client_socket.recv(1)
                if not chunk:
                    return
                line += chunk.decode('utf-8', errors='ignore')
            
            clean_line = line.strip()
            if in_data:
                if clean_line == ".":
                    in_data = False
                    print("\n" + "="*60)
                    print("RECEIVED EMAIL CONTENT:")
                    print(data_buffer.strip())
                    print("="*60 + "\n")
                    data_buffer = ""
                    client_socket.send(b"250 OK\r\n")
                else:
                    data_buffer += line
            else:
                if clean_line.upper().startswith("HELO") or clean_line.upper().startswith("EHLO"):
                    client_socket.send(b"250 Hello\r\n")
                elif clean_line.upper().startswith("MAIL FROM:"):
                    client_socket.send(b"250 OK\r\n")
                elif clean_line.upper().startswith("RCPT TO:"):
                    client_socket.send(b"250 OK\r\n")
                elif clean_line.upper() == "DATA":
                    in_data = True
                    client_socket.send(b"354 Start mail input; end with <CRLF>.<CRLF>\r\n")
                elif clean_line.upper() == "QUIT":
                    client_socket.send(b"221 Bye\r\n")
                    break
                else:
                    client_socket.send(b"250 OK\r\n")
    except Exception as e:
        print(f"Error handling SMTP client: {e}")
    finally:
        client_socket.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('127.0.0.1', 1025))
        server.listen(5)
        print("Mock SMTP server running on 127.0.0.1:1025. Press Ctrl+C to stop.")
    except Exception as e:
        print(f"Failed to start mock SMTP server on port 1025: {e}")
        sys.exit(1)
        
    try:
        while True:
            client, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client,))
            t.daemon = True
            t.start()
    except KeyboardInterrupt:
        print("\nStopping SMTP server.")
    finally:
        server.close()

if __name__ == '__main__':
    main()
