from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from datetime import datetime

from ..config import AppConfig

config = AppConfig()
SENDGRID_API_KEY = config.sendgrid_api_key
FROM_EMAIL = config.sendgrid_from_email

Host = config.base_url
href_faq = f"{Host}/support/solutions"

terms = f'''<a href="{Host}/terms-conditions" target="_blank">Terms</a>'''
privacy = f'''<a href="{Host}/privacy-policy" target="_blank">Privacy</a>'''
contact_us = f'''<a href="{Host}/contact-us" target="_blank">Contact Us</a>'''
faq = f'''<a href="{href_faq}" target="_blank">Faq</a>'''
support_email = '''<a href='mailto:support@minipix.in' target="_blank">support@minipix.in</a>'''


class Messages():

    @classmethod
    async def send_email(cls, to_email, subject, body):

        html_content = body + cls.footer_with_links(to_email)

        # the required message to be passed in html_content to parse the html tags.
        # to_emails value can also be a list of emails for a broadcast.
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )

        try:
            sg = SendGridAPIClient(api_key=SENDGRID_API_KEY)
            sg.send(message)

        except Exception as e:
            print(e)
        else:
            print("Email Sent")

    @classmethod
    def footer_with_links(cls, to_email):
        footer = f'''
        <br>
        {terms}  |  {privacy}  |  {contact_us}  <br><br>

        This message was emailed to {to_email} by MiniPIX because you created a MiniPIX account. <br><br>

        Best Regards,<br>
        MiniPIX Team<br>
        Email: {support_email}<br>
        '''
        return footer

    @classmethod
    def on_successful_registration(cls, user):
        subject = "Welcome To MiniPIX !!!"
        body = f'''
        Dear {user.get('name', 'Customer')},
        <br>
        <br>
        Welcome to <strong>MiniPIX!</strong> We are thrilled to have you join our community of entertainment. Get ready to start on an exciting journey filled with endless hours of entertainment, where you can stream your favorite movies, web series, and much more.<br>

        <strong>To purchase a subscription, simply follow the steps below:</strong><br>
        <ol type=1>
            <li>Open the MiniPIX app on your device.</li>
            <li>Navigate to the <a href="{Host}/account/subscriptions" target="_blank"><strong>"Subscription"</strong></a> or <a href="{Host}/account/subscriptions" target="_blank"><strong>"Upgrade"</strong></a> section within the app.</li>
            <li>Choose the subscription plan that best suits your preferences and budget.</li>
            <li>Select the payment method of your choice.</li>
            <li>Provide the necessary details for the payment, including your billing information.</li>
            <li>Confirm your subscription purchase.</li>
        </ol><br>
        Once your purchase is complete, you will gain immediate access to all the premium features and content available in the app. Whether you enjoy binge-watching your favorite TV series, discovering new movies, or exploring genres you love, our OTT app ensures a personalized and immersive entertainment experience.<br>

        Don't forget to enable notifications to stay updated on the latest releases, exclusive offers, and special events.<br>

        If you have any questions, concerns, or need assistance at any point, our dedicated customer support team is here to help. Feel free to reach out to us via support@minipix.in , and we'll be happy to assist you.<br><br>
        '''

        return subject, body

    @classmethod
    def on_successful_ticket_purchase(cls, user, details):
        content_type = details['type']
        url = f"{Host}/{content_type if content_type == 'series' else 'movies'}/{details['id']}"
        subject = "Your Ticket Purchase Confirmation - Enjoy the Show!"
        body = f'''
        Dear {user.get("name", "Customer")}<br>

        Thank you for choosing <strong>MiniPIX</strong> for your entertainment needs. We are excited to confirm your ticket purchase and look forward to providing you with an amazing viewing experience. Get ready to immerse yourself in the world of entertainment!<br>

        <strong>Here are the details of your ticket purchase:</strong><br>
        <ul type="disc">
            <li>{"Movie" if content_type == "movie" else "Series"} : <a href={url} target="_blank">{details["name"]}</a><br></li>
            <li>Expiry Date: {datetime.strptime(details["end"], '%Y-%m-%dT%H:%M:%S').strftime("%Y-%m-%d %H:%M")}</li>
        </ul><br>

        <strong>To access your purchased ticket(s), please follow these simple steps:</strong><br>
        <ol type="1">
            <li>Open the MiniPIX on your preferred device or visit our website at {Host}.</li>
            <li>Log in to your account using your registered  phone number or email address.</li>
            <li>Navigate to the "Tickets" section or a similar option in your account menu.</li>
            <li>Click on your purchased ticket and click on the corresponding details.</li>
            <li>Click To Watch and enjoy the show</li>
        </ol><br>

        Don't forget to enable notifications to stay updated on the latest releases, exclusive offers, and special events.<br>

        If you have any questions, concerns, or need assistance at any point, our dedicated customer support team is here to help. Feel free to reach out to us via {support_email}, and we'll be happy to assist you.<br><br>
        '''

        return subject, body

    @classmethod
    def on_successful_subsription_purchase(cls, user):
        subject = "Thank You for Subscribing to our MiniPIX!"
        body = f'''
        Dear {user.get("name", "Customer")}<br><br>

        We wanted to extend our heartfelt gratitude for subscribing to our <strong>MiniPIX</strong> app. Welcome to a world of limitless entertainment! We are thrilled to have you on board, and we can't wait for you to explore all the incredible content we have to offer.<br>

        <strong>Here are a few features and benefits you can enjoy as a subscriber:</strong><br>
        <ol type="1">
            <li>Ad-free streaming: Say goodbye to pesky interruptions and enjoy uninterrupted viewing pleasure.</li>
            <li>HD and Ultra HD streaming: Immerse yourself in stunning visuals and crystal-clear audio quality.</li>
            <li>Multi-device access: Access our app across multiple devices, including smartphones, tablets, and smart TVs, for a seamless streaming experience.</li>
            <li>Discover a wide range of genres on our MiniPIX app.</li>
        </ol>
       <br>Don't forget to enable notifications to stay updated on the latest releases, exclusive offers, and special events.<br>

        If you have any questions, concerns, or need assistance at any point, our dedicated customer support team is here to help. Feel free to reach out to us via support@minipix.in, and we'll be happy to assist you.<br><br>
        '''

        return subject, body

    @classmethod
    def on_subscription_expired(cls, user):
        subject = "Renew Your Subscription Plan for MiniPIX"
        body = f'''
        Dear {user.get("name", "Customer")}<br>

        We hope this email finds you well and that you have been enjoying <strong><a href="{Host}/account/subscriptions" target="_blank">MiniPIX</a></strong> for your entertainment needs. We appreciate your support and are delighted to offer you the opportunity to renew your subscription for another exciting period of uninterrupted access to our extensive collection of movies, web series, and exclusive content.<br>

        <strong>To renew your subscription, simply follow these steps:</strong><br>
        <ol type="1">
            <li>Visit our official website or open the <a href="{Host}" target="_blank"><strong>MiniPIX</strong></a> on your device.</li>
            <li>Sign in to your account using your registered phone number or email address.</li>
            <li>Navigate to the subscription section within your account settings.</li>
            <li>Select the renewal option and follow the prompts to complete the process.</li>
        </ol><br>
        Thank you for being a valued member of our <strong>MiniPIX<strong> community. We look forward to continuing to serve you with the best entertainment experience possible.<br><br>
        '''
        return subject, body

    # Realtime emails as background tasks.
    @classmethod
    def on_ticket_purchase(cls, details):
        content_type = details['type']
        url = f"{Host}/{content_type if content_type == 'series' else 'movies'}/{details['id']}"
        subject = "Namaste 🙏  MiniPIX welcomes you..."
        body = f'''
        Hello,<br><br>

        We welcome you on our ship to unparalleled entertainment - Hum hain "Dil se Desi !"<br>
        Start watching, pause, then pick up right where you left off on the same device or another device that connects to MiniPIX.<br><br>

        TICKET Details:<br>
        Movie/Series Name - {details['name']}<br>
        Expires on - {details['end']}<br>
        Order ID - {details['order_id']}<br><br>

        <a href="{url}" target="_blank">Enjoy Watching Content</a><br><br>
        '''
        return subject, body

    @classmethod
    def on_successful_upgrade(cls, user):
        subject = "Congratulations on Upgrading Your Subscription in MiniPIX App"
        body = f'''
        Dear {user.get("name", "Customer")}<br>

        We very happy to inform you that your subscription upgrade has been successfully .Congratulations and thank you for choosing to enhance your streaming experience with us.<br>

        <strong>With your upgraded subscription, you now have access to a wide range of exciting features and exclusive content that will take your entertainment journey. We're excited to share with you all the benefits you can enjoy:</strong><br>
        <ol type="1">
            <li>Ad-Free Streaming: Say goodbye to interruptions and enjoy uninterrupted streaming of your favorite shows and movies without any advertisements.</li>
            <li>Streaming Quality: Immerse yourself in the highest quality visuals and audio with options for Ultra HD and 4K streaming.</li>
            <li>Multiple Device Support: Stream content simultaneously on multiple devices, allowing your family and friends to enjoy their favorite shows alongwith you.</li>
        </ol><br>

        If you have any questions, concerns, or need assistance at any point, our dedicated customer support team is here to help. Feel free to reach out to us via {support_email}, and we'll be happy to assist you.<br><br>
        '''

        return subject, body

    @classmethod
    def on_cancellation_of_subscription(cls, user):
        subject = "MiniPIX :Confirmation of Subscription Cancellation"
        body = f'''
        Dear {user.get("name", "Customer")}, <br>

        We hope this email finds you well. We want to inform you that your subscription to our MiniPIX app and it has been successfully canceled as per your request. We're sorry to see you go, and we appreciate the time you spent with you.<br>

        Your cancellation request has been processed, and your account will no longer be billed for the MiniPIX app subscription. Please note that you will lose access to our premium content immediately.<br>

        If you ever decide to return and reactivate your subscription, please don't hesitate to reach out to us<br> 

        Once again, thank you for choosing our MiniPIX app. We wish you all the best and hope to serve you again in the future.<br><br>

        '''

        return subject, body
