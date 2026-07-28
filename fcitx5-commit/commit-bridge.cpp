#include "commit-bridge.h"
#include <fcitx-utils/event.h>
#include <fcitx/addonfactory.h>
#include <fcitx/addonmanager.h>
#include <fcitx/inputcontextmanager.h>
#include <fcitx/event.h>
#include <fstream>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <unistd.h>

namespace fcitx {

CommitBridge::CommitBridge(Instance *instance)
    : instance_(instance) {

    eventHandlers_.emplace_back(instance_->watchEvent(
        EventType::InputContextKeyEvent, EventWatcherPhase::Default,
        [this](Event &event) {
            auto &keyEvent = static_cast<KeyEvent &>(event);
            if (keyEvent.isRelease()) return;
            lastFocusedIc_ = keyEvent.inputContext()->watch();
        }));

    eventHandlers_.emplace_back(instance_->watchEvent(
        EventType::InputContextFocusIn, EventWatcherPhase::Default,
        [this](Event &event) {
            auto &icEvent = static_cast<InputContextEvent &>(event);
            lastFocusedIc_ = icEvent.inputContext()->watch();
        }));

    system("mkdir -p /tmp/voxtype 2>/dev/null");

    inotifyFd_ = inotify_init();
    if (inotifyFd_ < 0) return;

    watchFd_ = inotify_add_watch(inotifyFd_, "/tmp/voxtype",
                                 IN_CLOSE_WRITE | IN_CREATE);
    if (watchFd_ < 0) {
        close(inotifyFd_);
        inotifyFd_ = -1;
        return;
    }

    ioSource_ = instance_->eventLoop().addIOEvent(
        inotifyFd_, IOEventFlag::In,
        [this](EventSourceIO *, int fd, IOEventFlags) {
            char buf[sizeof(struct inotify_event) + 1024];
            ssize_t len = read(fd, buf, sizeof(buf));
            if (len <= 0) return true;

            size_t offset = 0;
            while (offset < static_cast<size_t>(len)) {
                auto *ev = reinterpret_cast<struct inotify_event *>(buf + offset);
                offset += sizeof(struct inotify_event) + ev->len;
                if (ev->len == 0 || std::string(ev->name) != "commit")
                    continue;

                std::ifstream rfile("/tmp/voxtype/result");
                if (rfile.is_open()) {
                    std::string text(
                        (std::istreambuf_iterator<char>(rfile)),
                        std::istreambuf_iterator<char>());
                    if (!text.empty()) {
                        commitText(text);
                    }
                }
                break;
            }
            return true;
        });
}

CommitBridge::~CommitBridge() {
    if (inotifyFd_ >= 0) close(inotifyFd_);
}

void CommitBridge::commitText(const std::string &text) {
    if (lastFocusedIc_.isValid()) {
        if (auto *ic = lastFocusedIc_.get()) {
            ic->commitString(text);
            return;
        }
    }
    auto *ic = instance_->mostRecentInputContext();
    if (ic) {
        ic->commitString(text);
        return;
    }
    instance_->inputContextManager().foreachFocused(
        [&text](InputContext *ic) {
            ic->commitString(text);
            return false;
        });
}

class CommitBridgeFactory : public AddonFactory {
public:
    AddonInstance *create(AddonManager *manager) override {
        return new CommitBridge(manager->instance());
    }
};

} // namespace fcitx

FCITX_ADDON_FACTORY_V2(commitbridge, fcitx::CommitBridgeFactory);
