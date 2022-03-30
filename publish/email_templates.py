verify_subject = 'CRAVAT: email verification'
verify_html=\
"""
<html>
    <head></head>
    <body>
        <p>
            <a href="{0}">Click here</a> to verify your email address.
        </p>
    </body>
</html>
"""
verify_text = 'Use the following link to verify your email_address:\n{0}'

reset_subject = 'CRAVAT: reset password'
reset_html=\
"""
<html>
    <head></head>
    <body>
        <p>
            <a href="{0}">Click here</a> to reset your CRAVAT password.
        </p>
    </body>
</html>
"""
reset_text='Use the following link to reset your CRAVAT password:\n{0}'

publish_received_subject='CRAVAT: submission received'
publish_received_html=\
"""
<html>
    <head></head>
    <body>
        <h1>
            Module Upload Revieved
        </h1>
        <br>
        <p>
            Your submission of {0}:{1} has been received. It is currently being processed. You will be notified through email at {2} when it is ready for download.
        </p>
    </body>
</html>
"""
publish_received_text='Your submission of {0}:{1} has been received by the CRAVAT store and is being processed.\nYou will be notified by email at {2} when it is ready for download.'

publish_success_subject='CRAVAT: submission completed'
publish_success_html=\
"""
<html>
    <head></head>
    <body>
        <h1>
            Module upload succeeded
        </h1>
        <br>
        <p>
            Your submission of {0}:{1} has been processed and is ready for download.
        </p>
    </body>
</html>
"""
publish_success_text='Your submission of {0}:{1} has been processed and is ready for download.'

publish_fail_subject='CRAVAT: submission failed'
publish_fail_html=\
"""
<html>
    <head></head>
    <body>
        <h1 style="color:red;">
            Module upload failed
        </h1>
        <br>
        <p>
            Your submission of {0}:{1} failed. Please check to make sure that your submission was properly formatted and try again. If the failure persists, contact the CRAVAT development team.
        </p>
    </body>
</html>
"""
publish_fail_text='Your submission of {0}:{1} failed. Please check to make sure that your submission was properly formatted and try again. If the failure persists, contact the CRAVAT development team.'
