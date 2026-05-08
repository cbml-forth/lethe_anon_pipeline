package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math/rand/v2"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"

	"github.com/devilcove/configuration"
	containerTypes "github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/client"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// App struct
type App struct {
	ctx context.Context
	cli *client.Client
}

type Config struct {
	SiteID         string `yaml:"site_id"`
	PsedonymPrefix string `yaml:"pseudonym_prefix"`
}

func letheAppDir() string {
	progName := filepath.Base(os.Args[0])
	userConfigDir, err := os.UserConfigDir()
	if err != nil {
		panic(fmt.Errorf("configuration dir %w", err))
	}
	return filepath.Join(userConfigDir, progName)
}

func makeSureConfigDirExists() {
	configDir := letheAppDir()
	if configDirStat, err := os.Stat(configDir); err != nil || !configDirStat.IsDir() {
		if err := os.MkdirAll(configDir, 0o700); err != nil {
			panic(err)
		}
	}
	configFile := filepath.Join(configDir, ConfigFileName)
	if _, err := os.Stat(configFile); err != nil {
		// Config file does not exist
		cfg := Config{
			SiteID:         "TEST",
			PsedonymPrefix: "{site_id}_",
		}
		if err := configuration.Save(&cfg, ConfigFileName); err != nil {
			log.Fatal(err)
		}
	}

}

var ConfigFileName = "config.yaml"

func readConfig() Config {
	makeSureConfigDirExists()

	var cfg Config
	if err := configuration.Get(&cfg, ConfigFileName); err != nil {
		log.Fatal(err)
	}
	return cfg
}
func saveConfig(cfg Config) error {
	if err := configuration.Save(&cfg, ConfigFileName); err != nil {
		log.Fatal(err)
	}
	return nil
}

// NewApp creates a new App application struct
func NewApp() *App {
	return &App{}
}

// startup is called at application startup
func (a *App) startup(ctx context.Context) {

	cfg := readConfig()
	fmt.Println("Configuration", cfg)

	// Perform your setup here
	a.ctx = ctx
	a.cli = nil

	cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		log.Fatal(err)
		a.shutdown(ctx)
	}
	a.cli = cli

}

// domReady is called after front-end resources have been loaded
func (a App) domReady(ctx context.Context) {
	// Add your action here
	config := readConfig()

	jsonBytes, _ := json.Marshal(config)
	// Inject as a global variable before frontend logic runs
	runtime.WindowExecJS(ctx, fmt.Sprintf("window.__APP_CONFIG__ = %s;", string(jsonBytes)))

}

// beforeClose is called when the application is about to quit,
// either by clicking the window close button or calling runtime.Quit.
// Returning true will cause the application to continue, false will continue shutdown as normal.
func (a *App) beforeClose(ctx context.Context) (prevent bool) {
	return false
}

// shutdown is called at application termination
func (a *App) shutdown(ctx context.Context) {
	if a.cli != nil {
		a.cli.Close()
	}
}

func (a *App) ListContainers() []containerTypes.Summary {
	ctx := context.Background()
	cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		panic(err)
	}
	defer cli.Close()

	containers, err := cli.ContainerList(ctx, containerTypes.ListOptions{
		Filters: filters.NewArgs(filters.Arg("status", "exited")),
	})
	if err != nil {
		panic(err)
	}

	return containers
}

type ContainerParams struct {
	Image        string
	SiteID       string
	InputDir     string
	OutputDir    string
	Pseudonymize bool
}

type ContainerStatus struct {
	ID     string
	Status string
	Error  string
	Logs   string
}

func (a *App) RunContainer(params *ContainerParams) ContainerStatus {
	ctx := context.Background()
	cli := a.cli

	// image := "hello-world"
	// cmd := []string{} // "run --help"
	env := []string{}

	os.UserConfigDir()
	cmd := []string{
		"run",
		params.SiteID,
		"-v",
	}
	if params.Pseudonymize {
		cmd = append(cmd, "--pseudonymize")
		cmd = append(cmd, "--pseudonym-prefix={site_id}")
	}

	var letheCfg = readConfig()
	letheCfg.SiteID = params.SiteID
	saveConfig(letheCfg)

	// // Ensure image is available (pull if necessary)
	// reader, err := cli.ImagePull(ctx, image, imageTypes.PullOptions{})
	// if err == nil && reader != nil {
	// 	// discard output
	// 	io.Copy(io.Discard, reader)
	// 	reader.Close()
	// }

	binds := []string{
		params.InputDir + ":/input:ro",
		params.OutputDir + ":/output",
		letheAppDir() + ":/app/db", // For state-dir
	}
	cfg := &containerTypes.Config{
		Image: params.Image,
		Cmd:   cmd,
		Env:   env,
	}
	hostCfg := &containerTypes.HostConfig{
		Binds: binds,
	}

	name := "lethe-" + strconv.Itoa(rand.IntN(1000))

	var mounts []string
	for _, s := range binds {
		mounts = append(mounts, "-v "+s)
	}
	fmt.Printf("Docker run command: docker run %s -it %s %s\n",
		strings.Join(mounts, " "),
		params.Image,
		strings.Join(cmd, " "))

	resp, err := cli.ContainerCreate(ctx, cfg, hostCfg, nil, nil, name)
	if err != nil {
		return ContainerStatus{"", "not-started", err.Error(), ""}
	}
	fmt.Printf("Container name : %s ID: %s", name, resp.ID)

	if err := cli.ContainerStart(ctx, resp.ID, containerTypes.StartOptions{}); err != nil {
		return ContainerStatus{resp.ID, "not-started", err.Error(), ""}
	}

	return ContainerStatus{resp.ID, "starting", "", ""}
}
func (a *App) GetContainerStatus(containerID string) string {
	ctx := context.Background()
	cli := a.cli

	resp, err := cli.ContainerInspect(ctx, containerID)
	if err != nil {
		return "failed"
	}

	run_statuses := []string{"created", "running", "paused", "restarting"}
	if slices.Contains(run_statuses, resp.State.Status) {
		return "running"
	}
	// case "created", "running", "paused", "restarting", "removing", "exited", or "dead"
	if resp.State.Status == "exited" || resp.State.Status == "dead" {
		if resp.State.ExitCode != 0 || resp.State.OOMKilled {
			return "failed"
		}
		return "finished"

	}
	return "failed"

}

func (a *App) SelectDirectory() string {

	dir, err := runtime.OpenDirectoryDialog(a.ctx, runtime.OpenDialogOptions{
		Title:                      "Select Input folder",
		ShowHiddenFiles:            false,
		CanCreateDirectories:       false,
		ResolvesAliases:            true,
		TreatPackagesAsDirectories: false,
	})
	if err != nil {
		panic(err)
	}

	return dir
}
