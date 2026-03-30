import launch

if not launch.is_installed("send2trash"):
    launch.run_pip("install send2trash==1.8.2", "send2trash")
