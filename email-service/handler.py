import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def send_email(event, context):
    try:
        # Get request body (decoded by serverless-offline)
        body_str = event.get('body', '')
        if not body_str:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'message': 'Missing request body'})
            }
        
        # Parse body
        try:
            body = json.loads(body_str)
        except Exception:
            # If serverless-offline already parsed it as a dict
            if isinstance(body_str, dict):
                body = body_str
            else:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'message': 'Invalid JSON in request body'})
                }
                
        trigger_type = body.get('trigger_type')
        recipient_email = body.get('recipient_email')
        data = body.get('data', {})
        
        if not trigger_type or not recipient_email:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'message': 'Missing trigger_type or recipient_email'})
            }
        
        # Prepare email details
        subject = ""
        html_content = ""
        
        if trigger_type == 'SIGNUP_WELCOME':
            subject = "Welcome to Mini HMS!"
            name = data.get('name', 'User')
            role = data.get('role', 'patient')
            html_content = f"""
            <html>
                <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f1f5f9; padding: 2rem; color: #1e293b;">
                    <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 2.5rem; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <h2 style="color: #0ea5e9; margin-top: 0; font-size: 1.75rem;">Welcome to Mini HMS, {name}!</h2>
                        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 1.5rem 0;" />
                        <p style="font-size: 1rem; line-height: 1.6;">Thank you for signing up as a <strong>{role}</strong>.</p>
                        <p style="font-size: 1rem; line-height: 1.6;">You can now access your dashboard to manage your appointments, schedule availability, and sync with Google Calendar.</p>
                        <br />
                        <p style="font-size: 0.9rem; color: #64748b;">Best regards,<br />The Mini HMS Team</p>
                    </div>
                </body>
            </html>
            """
        elif trigger_type == 'BOOKING_CONFIRMATION':
            subject = "Booking Confirmation - Mini HMS"
            doctor_name = data.get('doctor_name')
            patient_name = data.get('patient_name')
            date = data.get('date')
            time = data.get('time')
            html_content = f"""
            <html>
                <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f1f5f9; padding: 2rem; color: #1e293b;">
                    <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 2.5rem; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <h2 style="color: #10b981; margin-top: 0; font-size: 1.75rem;">Appointment Confirmed!</h2>
                        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 1.5rem 0;" />
                        <p style="font-size: 1rem; line-height: 1.6;">An appointment has been successfully booked with the following details:</p>
                        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.25rem; margin: 1.5rem 0;">
                            <ul style="list-style-type: none; padding: 0; margin: 0; font-size: 1rem; line-height: 1.8;">
                                <li><strong>Doctor:</strong> Dr. {doctor_name}</li>
                                <li><strong>Patient:</strong> {patient_name}</li>
                                <li><strong>Date:</strong> {date}</li>
                                <li><strong>Time:</strong> {time}</li>
                            </ul>
                        </div>
                        <p style="font-size: 1rem; line-height: 1.6;">If either user connected their Google Calendar, this appointment is also synced automatically.</p>
                        <br />
                        <p style="font-size: 0.9rem; color: #64748b;">Best regards,<br />The Mini HMS Team</p>
                    </div>
                </body>
            </html>
            """
        else:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'message': f'Unknown trigger_type: {trigger_type}'})
            }
        
        # Load SMTP Configurations
        smtp_host = os.environ.get('SMTP_HOST', '127.0.0.1')
        smtp_port = int(os.environ.get('SMTP_PORT', '1025'))
        smtp_user = os.environ.get('SMTP_USER', '')
        smtp_password = os.environ.get('SMTP_PASSWORD', '')
        sender_email = os.environ.get('SENDER_EMAIL', 'noreply@minihms.com')
        
        # Send SMTP Email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if smtp_user and smtp_password:
                server.starttls()
                server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, [recipient_email], msg.as_string())
            
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': 'Email sent successfully via serverless',
                'trigger_type': trigger_type,
                'recipient': recipient_email
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'message': f'Error in serverless email dispatch: {str(e)}'})
        }
