#include <QGuiApplication>
#include <QCoreApplication>
#include <QAction>
#include <QProcess>
#include <QDateTime>
#include <QFileInfo>
#include <KGlobalAccel>

// 查找脚本文件：相对于应用位置或向上搜索
static QString findScript()
{
    // 首先尝试相对于应用的位置（如果从build目录启动）
    QFileInfo appDir(QCoreApplication::applicationDirPath());
    
    // 向上遍历目录，查找instant_transcribe/main.py
    QString currentPath = appDir.absolutePath();
    for (int i = 0; i < 5; ++i) {
        QString scriptPath = currentPath + "/instant_transcribe/main.py";
        if (QFileInfo::exists(scriptPath)) {
            return QFileInfo(scriptPath).absoluteFilePath();
        }
        
        // 向上移动一级目录
        QFileInfo parent(currentPath);
        QString parentPath = parent.path();
        if (parentPath == currentPath) {
            // 已到达根目录
            break;
        }
        currentPath = parentPath;
    }
    
    // 如果未找到，返回空字符串
    qWarning() << "Failed to find instant_transcribe/main.py";
    return QString();
}

// 查找Python可执行文件
static QString findPython()
{
    // 首先尝试相对于应用的venv
    QFileInfo appDir(QCoreApplication::applicationDirPath());
    
    // 向上遍历目录，查找venv/bin/python
    QString currentPath = appDir.absolutePath();
    for (int i = 0; i < 5; ++i) {
        QString pythonPath = currentPath + "/venv/bin/python";
        if (QFileInfo::exists(pythonPath)) {
            return QFileInfo(pythonPath).absoluteFilePath();
        }
        
        // 向上移动一级目录
        QFileInfo parent(currentPath);
        QString parentPath = parent.path();
        if (parentPath == currentPath) {
            // 已到达根目录
            break;
        }
        currentPath = parentPath;
    }
    
    // 如果未找到venv，尝试使用系统python
    qWarning() << "venv/bin/python not found, trying system python";
    return QString("python3");
}

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("instant-transcribe-helper"));
    app.setQuitOnLastWindowClosed(false);

    // 查找脚本和Python
    QString script = findScript();
    QString python = findPython();
    
    if (script.isEmpty()) {
        qWarning("instant-transcribe-helper: 找不到instant_transcribe/main.py，无法启动");
        return 1;
    }
    if (python.isEmpty()) {
        qWarning("instant-transcribe-helper: 找不到Python解释器，无法启动");
        return 1;
    }

    QAction *action = new QAction();
    action->setObjectName(QStringLiteral("toggle_transcribe"));
    action->setText(QStringLiteral("Toggle Transcription"));

    bool ok1 = KGlobalAccel::self()->setDefaultShortcut(
        action, {QKeySequence(Qt::META | Qt::Key_R)});
    bool ok2 = KGlobalAccel::self()->setShortcut(
        action, {QKeySequence(Qt::META | Qt::Key_R)});

    if (!ok1 && !ok2) {
        qWarning("global-shortcut-helper: 快捷键注册失败，可能已被占用");
    }

    QObject::connect(action, &QAction::triggered, [python, script]() {
        static qint64 last = 0;
        qint64 now = QDateTime::currentMSecsSinceEpoch();
        if (now - last < 500) return;  // 防抖：500ms内只触发一次
        last = now;
        QProcess::startDetached(python, {script});
    });

    return app.exec();
}
